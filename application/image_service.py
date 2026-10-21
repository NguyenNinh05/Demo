"""Application / Intelligence Layer - ImageService (image and text encoders).

Two encoders, each used for what it does best:

  encode(image)       photo -> vector with Marqo-FashionSigLIP, a CLIP-style model
                      trained on fashion products. Used for photo search
                      ("find this garment") and "similar products".
  encode_text(text)   Vietnamese sentence -> vector with the multilingual CLIP text
                      encoder; encode_semantic_many(images) puts the product photos
                      in the same space (CLIP ViT-B/32), so "áo khoác đi mưa" can be
                      compared with the photos (semantic text search).

Measured on the evaluation photos (data/query_images), FashionSigLIP finds the
right category for 70 % of photos of products that are not in the shop, against
56 % for plain CLIP ViT-B/32.

To make photo search robust, every photo (catalogue and customer) goes through
the same preprocessing:
  1. EXIF rotation, RGB
  2. crop to the garment: the background colour is estimated from the border and
     the bounding box of the pixels that differ from it is kept
  3. pad to a square with the background colour (no garment is cut off)
and the embedding is the average of the photo and its mirror image.
"""
import io
import threading

import numpy as np
from PIL import Image, ImageOps


class ImageService:

    def __init__(self, photo_model="hf-hub:Marqo/marqo-fashionSigLIP",
                 semantic_image_model="clip-ViT-B-32", text_model=None, device=None):
        self.photo_model_name = photo_model
        self.semantic_model_name = semantic_image_model
        self.text_model_name = text_model
        self.device = device
        self._photo = None                    # (model, transform) or SentenceTransformer
        self._semantic = None
        self._text = None
        self._lock = threading.Lock()         # one model call at a time (web requests run in threads)

    # ------------------------------------------------------------ models
    def _device(self):
        if self.device is None:
            import torch
            self.device = "mps" if torch.backends.mps.is_available() else (
                "cuda" if torch.cuda.is_available() else "cpu")
        return self.device

    @staticmethod
    def _sentence_transformer(name, device):
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(name, device=device)

    def _photo_model(self):
        if self._photo is None:
            if self.photo_model_name.startswith("hf-hub:"):
                import open_clip
                model, _, transform = open_clip.create_model_and_transforms(self.photo_model_name)
                self._photo = (model.to(self._device()).eval(), transform)
            else:
                self._photo = self._sentence_transformer(self.photo_model_name, self._device())
        return self._photo

    def _embed_photos(self, images):
        model = self._photo_model()
        if isinstance(model, tuple):
            import torch
            net, transform = model
            with torch.no_grad():
                x = torch.stack([transform(im) for im in images]).to(self._device())
                z = net.encode_image(x)
                return torch.nn.functional.normalize(z, dim=-1).cpu().numpy()
        return model.encode(images, batch_size=32, convert_to_numpy=True,
                            normalize_embeddings=True, show_progress_bar=False)

    # ------------------------------------------------------- preprocessing
    @staticmethod
    def load(image):
        if isinstance(image, Image.Image):
            img = image
        elif isinstance(image, (bytes, bytearray)):
            img = Image.open(io.BytesIO(image))
        else:
            img = Image.open(image)
        return ImageOps.exif_transpose(img).convert("RGB")

    @staticmethod
    def crop_to_object(img, threshold=28, margin=0.06):
        small = img.copy()
        small.thumbnail((256, 256))
        arr = np.asarray(small).astype(np.int16)
        border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
        bg = np.median(border, axis=0)
        mask = np.abs(arr - bg).max(axis=2) > threshold
        ys, xs = np.nonzero(mask)
        if len(xs) < 50:
            return img, tuple(int(c) for c in bg)
        h, w = mask.shape
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        area = (x1 - x0) * (y1 - y0) / (w * h)
        if not 0.05 < area < 0.97:
            return img, tuple(int(c) for c in bg)
        mx, my = int((x1 - x0) * margin), int((y1 - y0) * margin)
        sx, sy = img.width / w, img.height / h
        box = (max(0, (x0 - mx) * sx), max(0, (y0 - my) * sy),
               min(img.width, (x1 + mx) * sx), min(img.height, (y1 + my) * sy))
        return img.crop(tuple(int(v) for v in box)), tuple(int(c) for c in bg)

    def preprocess(self, image):
        img, bg = self.crop_to_object(self.load(image))
        side = max(img.size)
        square = Image.new("RGB", (side, side), bg)
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        return square.resize((256, 256), Image.BICUBIC)

    @staticmethod
    def _average_views(z, n):
        z = z.reshape(n, 2, -1).mean(axis=1)
        return z / np.linalg.norm(z, axis=1, keepdims=True)

    # ------------------------------------------------------------ encoding
    def encode_many(self, images, batch_size=32):
        """Photo-search embeddings (FashionSigLIP), photo + mirror image averaged."""
        out = []
        for i in range(0, len(images), batch_size):
            views = []
            for image in images[i:i + batch_size]:
                img = self.preprocess(image)
                views += [img, ImageOps.mirror(img)]
            with self._lock:
                z = self._embed_photos(views)
            out.append(self._average_views(z, len(views) // 2))
        return np.concatenate(out)

    def encode(self, image):
        return self.encode_many([image])[0]

    def encode_semantic_many(self, images):
        """Product photos in the multilingual CLIP space (for semantic text search)."""
        views = []
        for image in images:
            img = self.preprocess(image)
            views += [img, ImageOps.mirror(img)]
        with self._lock:
            if self._semantic is None:
                self._semantic = self._sentence_transformer(self.semantic_model_name,
                                                            self._device())
            z = self._semantic.encode(views, batch_size=32, convert_to_numpy=True,
                                      normalize_embeddings=True, show_progress_bar=False)
        return self._average_views(z, len(images))

    def encode_text(self, text):
        if not text or not self.text_model_name:
            return None
        with self._lock:
            if self._text is None:
                self._text = self._sentence_transformer(self.text_model_name, self._device())
            z = self._text.encode([text], convert_to_numpy=True, normalize_embeddings=True,
                                  show_progress_bar=False)
        return z[0]
