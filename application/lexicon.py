"""Application Layer - Vietnamese shopping lexicon used by the rule parser.

Every alias is written WITH accents. The parser also accepts the same alias
typed without accents, except when the accent-free form is ambiguous
("dep" = dép / đẹp, "tim" = tím / tìm, "den" = đen / đến, "hong" = hồng / hông):
those need a context word before them ("ao den", "mau tim").
"""

# ------------------------------------------------------------------ categories
# category_id -> aliases (ids must match the category table)
CATEGORIES = {
    "ao": ["áo"],
    "quan": ["quần"],
    "ao_phong": ["áo phông", "áo thun", "áo pull", "áo tshirt", "tshirt", "áo tee",
                 "áo phông trơn", "áo thun trơn", "áo cotton"],
    "ao_polo": ["áo polo", "polo", "áo thun có cổ", "áo phông có cổ", "áo cổ bẻ"],
    "ao_so_mi": ["áo sơ mi", "sơ mi", "sơmi", "áo sơmi", "áo somi", "shirt"],
    "ao_kieu": ["áo kiểu", "áo blouse", "blouse", "áo bánh bèo", "áo điệu", "áo nữ tính"],
    "ao_hai_day": ["áo hai dây", "áo 2 dây", "áo ba lỗ", "áo 3 lỗ", "áo tank top",
                   "tank top", "áo dây", "áo sát nách"],
    "ao_len": ["áo len", "áo sweater", "sweater", "áo dệt kim", "áo len dệt kim"],
    "ao_ni": ["áo nỉ", "áo sweatshirt", "sweatshirt", "áo nỉ bông"],
    "ao_hoodie": ["áo hoodie", "hoodie", "áo hoodies", "hoodies", "áo nỉ có mũ"],
    "ao_cardigan": ["áo cardigan", "cardigan", "áo khoác len", "áo len cài khuy"],
    "ao_khoac": ["áo khoác", "khoác", "jacket", "áo jacket", "áo măng tô", "măng tô",
                 "áo dạ", "áo phao", "áo gió", "áo bomber", "bomber", "áo parka", "parka",
                 "coat", "áo trench coat", "trench coat", "áo khoác ngoài", "áo chống nắng"],
    "ao_blazer": ["áo blazer", "blazer", "áo vest", "vest", "áo vét", "áo comple"],
    "quan_jeans": ["quần jeans", "quần jean", "quần bò", "quần denim", "jeans", "jean",
                   "quần rin", "quần zin",
                   # how speech recognisers often write "jean" said the Vietnamese way
                   "quần gian", "quần din", "quần jin", "quần dzin", "quần gin"],
    "quan_dai": ["quần dài", "quần kaki", "quần chino", "quần vải", "quần ống rộng",
                 "quần ống suông", "quần culottes", "pants", "trousers"],
    "quan_au": ["quần âu", "quần tây", "quần công sở", "quần vest", "quần vải âu"],
    "quan_jogger": ["quần jogger", "jogger", "joggers", "quần nỉ", "quần thể thao",
                    "quần bo gấu", "quần bo ống", "quần ống bo", "quần thun dài"],
    "quan_short": ["quần short", "quần shorts", "short", "shorts", "quần sooc", "quần soóc",
                   "quần sọt", "quần đùi", "quần ngắn", "quần cộc"],
    "quan_legging": ["quần legging", "legging", "leggings", "quần yoga", "quần tập gym",
                     "quần ôm tập"],
}

# products the shop does not sell (only tops and trousers)
UNSUPPORTED = {
    "váy": ["váy", "chân váy", "đầm", "váy liền", "đầm liền", "dress", "skirt"],
    "giày dép": ["giày", "dép", "giày dép", "sandal", "sneaker", "sneakers", "boot", "boots"],
    "túi ví": ["túi", "túi xách", "ví", "bóp", "balo", "ba lô", "cặp"],
    "phụ kiện": ["mũ", "nón", "kính", "kính râm", "đồng hồ", "thắt lưng", "dây nịt",
                 "trang sức", "vòng cổ", "khăn", "tất", "vớ", "nước hoa"],
    "đồ lót / đồ bơi": ["quần lót", "áo ngực", "áo lót", "đồ lót", "đồ bơi", "bikini",
                        "đồ ngủ", "pijama", "pyjama"],
    "jumpsuit": ["jumpsuit", "yếm", "quần yếm", "bộ liền"],
}

# --------------------------------------------------------------------- colours
# product.color value -> aliases
COLORS = {
    "đen": ["đen", "black", "đen tuyền"],
    "trắng": ["trắng", "white", "trắng tinh", "trắng sữa"],
    "be": ["be", "beige", "kem", "nude", "trắng kem", "off white"],
    "xám": ["xám", "ghi", "grey", "gray", "xám tro", "ghi xám", "xám lông chuột"],
    "xanh dương": ["xanh dương", "xanh lam", "xanh nước biển", "xanh biển", "xanh da trời",
                   "xanh navy", "navy", "xanh than", "xanh coban", "xanh jean", "xanh bò",
                   "blue", "xanh đen"],
    "xanh lá": ["xanh lá", "xanh lá cây", "xanh lục", "xanh lá mạ", "xanh cốm", "green"],
    "xanh rêu": ["xanh rêu", "rêu", "olive", "xanh lính", "xanh olive"],
    "xanh ngọc": ["xanh ngọc", "xanh mint", "mint", "xanh bạc hà", "turquoise"],
    "đỏ": ["đỏ", "red", "đỏ đô", "đỏ mận", "đỏ tươi", "đỏ rượu", "đỏ gạch"],
    "hồng": ["hồng", "pink", "hồng phấn", "hồng pastel", "hồng đất"],
    "nâu": ["nâu", "brown", "nâu đất", "nâu tây", "camel", "màu cà phê", "nâu sữa"],
    "vàng": ["vàng", "yellow", "vàng nghệ", "vàng chanh", "vàng mù tạt"],
    "cam": ["cam", "orange", "cam đất"],
    "tím": ["tím", "purple", "lilac", "lavender", "tím lavender"],
    "bạc": ["bạc", "silver", "ánh kim"],
}
GENERIC_COLORS = {"xanh": ["xanh dương", "xanh lá", "xanh rêu", "xanh ngọc"]}

# ---------------------------------------------------------------------- gender
GENDERS = {
    "nam": ["nam", "đàn ông", "con trai", "bạn trai", "men", "man", "boy", "nam giới",
            "phái mạnh", "chồng", "ông xã", "anh trai", "bố"],
    "nu": ["nữ", "phụ nữ", "con gái", "bạn gái", "women", "woman", "girl", "lady", "nữ giới",
           "phái đẹp", "vợ", "bà xã", "chị gái", "mẹ", "chị em"],
}

# -------------------------------------------------------- material and pattern
MATERIALS = {
    "cotton": ["cotton", "coton", "vải cotton", "chất cotton"],
    "linen": ["linen", "lanh", "vải lanh", "đũi", "vải đũi"],
    "denim": ["denim", "vải bò", "vải jean", "chất bò", "chất jean"],
    "len": ["len", "wool", "dạ", "len lông cừu", "cashmere", "dệt kim"],
    "nỉ": ["nỉ", "vải nỉ", "fleece"],
    "da": ["da", "leather", "da thật", "da lộn", "giả da"],
    "lụa": ["lụa", "satin", "silk", "phi lụa"],
    "voan": ["voan", "chiffon"],
    "nhung tăm": ["nhung", "nhung tăm", "corduroy", "nhung gân"],
    "kaki": ["kaki", "khaki", "twill", "vải kaki"],
    "thun": ["thun", "jersey", "vải thun"],
    "vải thể thao": ["vải thể thao", "vải thun lạnh", "dri fit", "vải nhanh khô", "thoáng khí"],
    "viscose": ["viscose", "rayon", "lụa nhân tạo"],
}
PATTERNS = {
    "trơn": ["trơn", "basic", "đơn sắc", "một màu", "plain"],
    "kẻ sọc": ["kẻ sọc", "sọc", "kẻ", "stripe", "striped", "sọc ngang", "sọc dọc", "kẻ ngang"],
    "kẻ caro": ["caro", "ca rô", "kẻ caro", "kẻ ca rô", "kẻ ô", "check", "sọc caro"],
    "họa tiết": ["họa tiết", "hoạ tiết", "hoa văn", "in hoa", "hoa nhí", "pattern", "floral"],
    "in hình": ["in hình", "in chữ", "graphic", "hình in", "có hình", "in logo", "print"],
    "chấm bi": ["chấm bi", "polka", "polka dot"],
    "ren": ["ren", "lace"],
    "thêu": ["thêu", "embroidery"],
    "phối màu": ["phối màu", "color block", "nhiều màu"],
}

# design details: canonical words that appear in the product descriptions
FEATURES = {
    "cổ tim": ["cổ tim", "cổ v", "cổ chữ v", "v neck", "vneck"],
    "cổ tròn": ["cổ tròn", "crew neck"],
    "cổ lọ": ["cổ lọ", "cổ cao", "turtleneck"],
    "có mũ": ["có mũ", "có nón", "mũ trùm", "hood"],
    "dài tay": ["dài tay", "tay dài", "long sleeve"],
    "ngắn tay": ["ngắn tay", "tay ngắn", "cộc tay", "tay cộc", "short sleeve"],
    "sát nách": ["sát nách", "không tay"],
    "dáng rộng": ["dáng rộng", "form rộng", "rộng", "oversize", "oversized", "boxy", "thụng",
                  "rộng rãi"],
    "dáng ôm": ["dáng ôm", "ôm", "ôm body", "body", "slim", "slimfit", "slim fit", "bó",
                "skinny", "ôm sát"],
    "croptop": ["croptop", "crop top", "crop", "áo lửng"],
    "khóa kéo": ["khóa kéo", "khoá kéo", "dây kéo", "zip", "có khóa"],
    "hai hàng khuy": ["hai hàng khuy", "2 hàng khuy", "hai hàng cúc"],
    "cạp cao": ["cạp cao", "lưng cao", "high waist"],
    "ống rộng": ["ống rộng", "ống loe", "loe"],
    "ống đứng": ["ống đứng", "ống suông", "ống thẳng", "straight"],
    "ống côn": ["ống côn", "côn"],
    "lửng": ["lửng", "ngố", "quần lửng"],
    "cạp chun": ["cạp chun", "lưng thun", "lưng chun", "cạp thun"],
    "rách": ["rách", "rách gối", "ripped"],
}

# occasions -> categories that fit (understanding WHY the customer buys)
OCCASIONS = {
    "đi làm": (["đi làm", "công sở", "văn phòng", "đi phỏng vấn", "phỏng vấn", "đi họp",
                "lịch sự", "thanh lịch"],
               ["ao_so_mi", "ao_blazer", "ao_kieu", "ao_polo", "quan_au"]),
    "tập thể thao": (["đi tập", "tập gym", "gym", "chạy bộ", "tập thể dục", "thể thao", "yoga",
                      "đá bóng", "đi bộ"],
                     ["quan_legging", "quan_jogger", "quan_short", "ao_phong", "ao_hoodie"]),
    "đi biển / trời nóng": (["đi biển", "đi chơi biển", "du lịch biển", "mùa hè", "trời nóng",
                             "nóng", "thoáng mát", "mát mẻ"],
                            ["ao_phong", "ao_hai_day", "quan_short", "ao_so_mi"]),
    "trời lạnh": (["mùa đông", "trời lạnh", "lạnh", "giữ ấm", "ấm áp", "rét", "thu đông",
                   "mùa thu"],
                  ["ao_len", "ao_khoac", "ao_hoodie", "ao_cardigan", "ao_ni"]),
    "đi tiệc / hẹn hò": (["đi tiệc", "dự tiệc", "đám cưới", "đi đám cưới", "sự kiện",
                          "hẹn hò", "đi date"],
                         ["ao_kieu", "ao_blazer", "ao_so_mi", "quan_au"]),
    "mặc ở nhà": (["ở nhà", "mặc nhà", "thoải mái"],
                  ["ao_phong", "quan_jogger", "quan_short", "ao_ni"]),
    "đi chơi / đi học": (["đi chơi", "dạo phố", "đi cà phê", "đi cafe", "đi học"],
                         ["ao_phong", "quan_jeans", "ao_so_mi", "ao_hoodie", "quan_short"]),
    "trời mưa / gió": (["đi mưa", "trời mưa", "mưa", "chống nước", "chống gió"],
                       ["ao_khoac"]),
}

SORTS = {
    "price_asc": ["rẻ nhất", "giá rẻ nhất", "giá thấp nhất", "rẻ", "giá rẻ", "rẻ rẻ",
                  "bình dân", "hạt dẻ", "giá mềm", "không đắt", "không mắc", "tiết kiệm",
                  "sinh viên"],
    "price_desc": ["đắt nhất", "mắc nhất", "giá cao nhất", "cao cấp", "xịn", "sang trọng",
                   "xịn nhất", "đắt tiền"],
    "popular": ["bán chạy", "phổ biến", "hot", "nổi bật", "nhiều người mua", "best seller",
                "bestseller", "hot trend", "trending", "được yêu thích"],
    "newest": ["mới nhất", "mới về", "hàng mới", "mẫu mới", "mới ra", "new arrival"],
}
IN_STOCK = ["còn hàng", "có sẵn", "sẵn hàng", "có hàng"]

# regional / spoken words -> standard Vietnamese (applied token by token)
DIALECT = {
    "hông": "không", "hổng": "không", "hem": "không", "hok": "không", "khum": "không",
    "hơm": "không", "ko": "không", "kh": "không", "khôg": "không", "k0": "không",
    "mắc": "đắt", "kiếm": "tìm", "coi": "xem", "dzậy": "vậy", "zậy": "vậy", "rứa": "vậy",
    "răng": "sao", "mô": "nào", "nớ": "đó", "tê": "kia", "đặng": "để",
    "ngàn": "nghìn", "zin": "jean", "rin": "jean", "sọt": "short", "bự": "rộng",
}

# accent-free single words that are too ambiguous without a context word
AMBIGUOUS = {"dep", "tim", "den", "do", "hong", "be", "bac", "cam", "vang", "trang", "len",
             "vay", "dam", "tui", "vi", "mu", "non", "tat", "da", "kem", "reu", "ke",
             "loe", "con", "om", "bo", "re", "ren", "lanh", "nhung"}

STOP_WORDS = set("""
tìm kiếm cho tôi mình em anh chị tớ bạn xem muốn cần mua có không ạ à ơi nhé nha nhen
nghen với giúp giùm dùm mấy cái chiếc bộ đồ những các một vài nào gì sao đi nè đó này kia
shop loại mẫu kiểu sản phẩm hàng giá tiền màu size đẹp xinh ok được bao nhiêu là thì mà và
hoặc hay của để trong về ra vô vào vậy thế nhỉ đâu đang đã sẽ rồi nữa luôn lắm quá rất thật
hơi mặc ưng thích cute dễ thương lấy hãy làm ơn xin chào phù hợp dành bên khoảng tầm chừng
từ đến tới dưới trên hơn nhất thử giá cả please show find me want i the a an for with some
of in to and is are my looking need search có thể nhé ạ order chất vải bằng kiếm hỏi biết
còn gửi thêm nên chọn nhìn trông giống như tui tao ni chi nhiêu nhưng tương tự y chang
hệt kiểu cũng khác ảnh hình
""".split())

ORDER_LATEST = ["gần nhất", "mới nhất", "gần đây", "vừa đặt", "mới đặt", "cuối cùng",
                "lần trước", "hôm qua", "vừa mua", "mới mua"]
ORDER_ALL = ["các đơn", "tất cả đơn", "những đơn", "lịch sử", "đã mua", "danh sách đơn"]
