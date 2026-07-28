"""Seed restaurants into ChromaDB for semantic search. Covers Chengdu, Beijing, Shanghai, Xi'an."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

City = "成都"
CHENGDU_RESTAURANTS = [
    # ── 川菜/火锅 ──
    {"name": "小龙翻大江火锅", "area": "宽窄巷子", "cuisine": "火锅", "description": "宽窄巷子里的文化火锅，三层庭院、雕梁画栋、龙形铜雕，环境和菜品都极具仪式感。", "avg_price_per_person_cny": 150, "rating": 4.6, "location": {"lat": 30.6750, "lng": 104.0535}, "must_try_dishes": ["翻江毛肚", "九尺鹅肠", "冰粉"]},
    {"name": "蜀大侠火锅", "area": "春熙路", "cuisine": "火锅", "description": "成都人气最高的重庆牛油火锅之一，武侠主题，锅底麻辣醇厚，生意火爆需排队。", "avg_price_per_person_cny": 120, "rating": 4.5, "location": {"lat": 30.6565, "lng": 104.0800}, "must_try_dishes": ["花千骨", "冰川鹅肠", "大刀肝片"]},
    {"name": "大龙燚火锅", "area": "春熙路", "cuisine": "火锅", "description": "成都老牌重庆火锅品牌，锅底重油重辣，是检验吃辣能力的标杆，也有微辣选择。", "avg_price_per_person_cny": 130, "rating": 4.5, "location": {"lat": 30.6555, "lng": 104.0820}, "must_try_dishes": ["屠场鲜毛肚", "极品鹅肠", "耗儿鱼"]},
    {"name": "马路边边麻辣烫", "area": "九眼桥", "cuisine": "串串香", "description": "复古8090年代怀旧风的串串店，搪瓷杯、红砖墙、小卖部零食，锅底越吃越香。", "avg_price_per_person_cny": 80, "rating": 4.4, "location": {"lat": 30.6430, "lng": 104.0890}, "must_try_dishes": ["嫩牛肉", "小郡肝", "脆皮肠"]},
    {"name": "冒椒火辣", "area": "奎星楼街", "cuisine": "串串香", "description": "奎星楼街的人气冷锅串串，兔头和兔腰是招牌，几乎每天排长队。", "avg_price_per_person_cny": 70, "rating": 4.5, "location": {"lat": 30.6720, "lng": 104.0540}, "must_try_dishes": ["兔头", "纠结千层肚", "爆浆兔腰"]},

    # ── 地道川菜 ──
    {"name": "陈麻婆豆腐", "area": "青羊宫", "cuisine": "川菜", "description": "创建于1862年的中华老字号，麻婆豆腐的发源地，豆腐嫩白麻辣鲜香，是成都人从小吃到大的味道。", "avg_price_per_person_cny": 80, "rating": 4.5, "location": {"lat": 30.6660, "lng": 104.0530}, "must_try_dishes": ["麻婆豆腐", "夫妻肺片", "宫保鸡丁"]},
    {"name": "蜀九香", "area": "锦里", "cuisine": "川菜", "description": "锦里商圈的高端新派川菜，将传统川菜与现代烹饪结合，环境中式典雅。", "avg_price_per_person_cny": 200, "rating": 4.5, "location": {"lat": 30.6430, "lng": 104.0460}, "must_try_dishes": ["鱼香龙虾", "花椒冰淇淋", "开水白菜"]},
    {"name": "钦善斋", "area": "武侯祠", "cuisine": "川菜", "description": "武侯祠附近的药膳主题餐厅，将川菜与中医养生理念结合，汤品尤为一绝。", "avg_price_per_person_cny": 120, "rating": 4.4, "location": {"lat": 30.6450, "lng": 104.0480}, "must_try_dishes": ["天麻炖鸡", "黄芪蒸鱼", "枸杞银耳汤"]},
    {"name": "盘飧市", "area": "春熙路", "cuisine": "川菜", "description": "成都百年老字号的卤菜馆，腌卤熟食闻名全城，外卖窗口常年排队。", "avg_price_per_person_cny": 60, "rating": 4.4, "location": {"lat": 30.6578, "lng": 104.0815}, "must_try_dishes": ["卤鸭子", "卤猪蹄", "烟熏排骨"]},
    {"name": "巴国布衣", "area": "高新区", "cuisine": "川菜", "description": "新派川菜的代表品牌，在传统基础上融入创新元素，环境有川剧变脸表演。", "avg_price_per_person_cny": 100, "rating": 4.3, "location": {"lat": 30.5780, "lng": 104.0630}, "must_try_dishes": ["毛血旺", "三峡石爆脆肠", "锅巴肉片"]},

    # ── 小吃 ──
    {"name": "龙抄手", "area": "春熙路", "cuisine": "小吃", "description": "成都著名小吃店，一个抄手多种吃法：红油、清汤、海味，还有各类成都小吃套餐。", "avg_price_per_person_cny": 40, "rating": 4.3, "location": {"lat": 30.6568, "lng": 104.0810}, "must_try_dishes": ["红油抄手", "钟水饺", "担担面"]},
    {"name": "小谭豆花", "area": "青羊宫", "cuisine": "小吃", "description": "成都老字号豆花店，冰醉豆花夏天吃最爽，馓子豆花咸香酥脆，品种丰富。", "avg_price_per_person_cny": 25, "rating": 4.4, "location": {"lat": 30.6650, "lng": 104.0510}, "must_try_dishes": ["冰醉豆花", "馓子豆花", "夫妻肺片"]},
    {"name": "洞子口张老二凉粉", "area": "文殊院", "cuisine": "小吃", "description": "文殊院旁的几十年老店，甜水面和凉粉是成都人心中的白月光，每天客人络绎不绝。", "avg_price_per_person_cny": 25, "rating": 4.5, "location": {"lat": 30.6745, "lng": 104.0700}, "must_try_dishes": ["甜水面", "白凉粉", "黄凉粉"]},
    {"name": "赖汤圆", "area": "春熙路", "cuisine": "小吃", "description": "成都百年老字号汤圆店，糯米软糯，馅料丰富，有芝麻、玫瑰、花生等多种口味。", "avg_price_per_person_cny": 30, "rating": 4.2, "location": {"lat": 30.6570, "lng": 104.0820}, "must_try_dishes": ["芝麻汤圆", "玫瑰汤圆", "红糖糍粑"]},

    # ── 异国/其他 ──
    {"name": "大德酒肴", "area": "太古里", "cuisine": "日料", "description": "太古里内的中高端日料，刺身新鲜空运，环境日式极简，午餐定食性价比高。", "avg_price_per_person_cny": 250, "rating": 4.4, "location": {"lat": 30.6535, "lng": 104.0840}, "must_try_dishes": ["特上刺身拼盘", "鳗鱼饭", "抹茶布丁"]},
    {"name": "祖母的厨房", "area": "桐梓林", "cuisine": "西餐", "description": "成都老牌美式西餐厅，氛围温馨，牛排和汉堡用料扎实，是成都外国人的食堂。", "avg_price_per_person_cny": 150, "rating": 4.3, "location": {"lat": 30.6000, "lng": 104.0600}, "must_try_dishes": ["肉眼牛排", "牛肉汉堡", "南瓜汤"]},
    {"name": "苏坦土耳其餐厅", "area": "九眼桥", "cuisine": "中东菜", "description": "成都少有的正宗土耳其菜，烤肉和鹰嘴豆泥地道，靠窗位可看锦江夜景。", "avg_price_per_person_cny": 120, "rating": 4.3, "location": {"lat": 30.6435, "lng": 104.0900}, "must_try_dishes": ["烤肉拼盘", "鹰嘴豆泥", "土耳其红茶"]},
    {"name": "Joel Robuchon 侯布雄", "area": "高新区", "cuisine": "法餐", "description": "米其林三星主厨的法餐厅，位于华尔道夫酒店，是成都最高端的fine dining体验之一。", "avg_price_per_person_cny": 800, "rating": 4.7, "location": {"lat": 30.5800, "lng": 104.0670}, "must_try_dishes": ["鱼子酱", "松露土豆泥", "巧克力塔"]},
]

City = "北京"
BEIJING_RESTAURANTS = [
    # ── 烤鸭/京菜 ──
    {"name": "全聚德烤鸭前门店", "area": "前门", "cuisine": "京菜", "description": "创建于1864年的中华老字号，北京烤鸭的代名词，挂炉烤鸭皮脆肉嫩，有文化展示。", "avg_price_per_person_cny": 200, "rating": 4.3, "location": {"lat": 39.8950, "lng": 116.3960}, "must_try_dishes": ["全聚德烤鸭", "芥末鸭掌", "鸭四宝"]},
    {"name": "大董烤鸭工体店", "area": "三里屯", "cuisine": "京菜", "description": "新派烤鸭的旗帜，首创酥不腻烤鸭皮，环境艺术化，分子料理与传统中餐的完美结合。", "avg_price_per_person_cny": 350, "rating": 4.6, "location": {"lat": 39.9310, "lng": 116.4500}, "must_try_dishes": ["酥不腻烤鸭", "董氏烧海参", "糖醋小排"]},
    {"name": "四季民福烤鸭故宫店", "area": "东华门", "cuisine": "京菜", "description": "故宫东华门旁的人气烤鸭店，景观位可直接看到故宫角楼，赏美景吃烤鸭的人气之选。", "avg_price_per_person_cny": 160, "rating": 4.5, "location": {"lat": 39.9140, "lng": 116.4020}, "must_try_dishes": ["烤鸭", "宫廷小吃拼盘", "巧拌豆苗"]},
    {"name": "局气", "area": "西单", "cuisine": "京菜", "description": "以北京为主题的新派京菜，菜品创意十足，蜂窝煤炒饭点火即燃，老北京氛围浓郁。", "avg_price_per_person_cny": 120, "rating": 4.4, "location": {"lat": 39.9140, "lng": 116.3750}, "must_try_dishes": ["蜂窝煤炒饭", "小吊梨汤", "炒肝儿"]},
    {"name": "厉家菜", "area": "后海", "cuisine": "京菜", "description": "后海羊房胡同里的宫廷私房菜，末代皇帝溥仪御厨后人所创，需提前预约，体验皇室菜肴。", "avg_price_per_person_cny": 500, "rating": 4.5, "location": {"lat": 39.9380, "lng": 116.3830}, "must_try_dishes": ["燕窝羹", "黄焖鱼翅", "京味龙虾"]},

    # ── 涮羊肉 ──
    {"name": "聚宝源", "area": "牛街", "cuisine": "涮羊肉", "description": "牛街人气最旺的涮肉馆，肉质鲜嫩无膻味，手切羊肉是招牌，烧饼也烤得极好。", "avg_price_per_person_cny": 130, "rating": 4.6, "location": {"lat": 39.8840, "lng": 116.3610}, "must_try_dishes": ["手切鲜羊肉", "牛百叶", "烧饼"]},
    {"name": "南门涮肉", "area": "南二环", "cuisine": "涮羊肉", "description": "天坛南门外的老北京铜锅涮肉，大铜锅炭火涮肉，麻酱小料是灵魂，冬天排队两小时起。", "avg_price_per_person_cny": 120, "rating": 4.5, "location": {"lat": 39.8730, "lng": 116.4100}, "must_try_dishes": ["手切羊肉", "肥牛", "糖蒜"]},

    # ── 小吃/早餐 ──
    {"name": "姚记炒肝", "area": "鼓楼", "cuisine": "小吃", "description": "鼓楼旁几十年的北京小吃店，炒肝儿蒜香浓郁，包子皮薄馅大，游客和本地人都爱。", "avg_price_per_person_cny": 35, "rating": 4.2, "location": {"lat": 39.9410, "lng": 116.3960}, "must_try_dishes": ["炒肝儿", "猪肉大葱包子", "炸灌肠"]},
    {"name": "海碗居", "area": "王府井", "cuisine": "小吃", "description": "百年历史的北京炸酱面馆，八碟菜码配手擀面，服务员吆喝一声'来啦您呐'满屋京味儿。", "avg_price_per_person_cny": 60, "rating": 4.3, "location": {"lat": 39.9120, "lng": 116.4150}, "must_try_dishes": ["炸酱面", "芥末墩儿", "豌豆黄"]},
    {"name": "护国寺小吃总店", "area": "护国寺", "cuisine": "小吃", "description": "北京清真小吃的集大成者，品种超过100种，豌豆黄和驴打滚最受欢迎。", "avg_price_per_person_cny": 40, "rating": 4.2, "location": {"lat": 39.9350, "lng": 116.3690}, "must_try_dishes": ["豌豆黄", "驴打滚", "艾窝窝"]},

    # ── 异国/高端 ──
    {"name": "TRB Hutong", "area": "东城", "cuisine": "法餐", "description": "嵩祝寺内的米其林星級法餐厅，600年古寺与现代法餐的碰撞，是北京最浪漫的用餐地之一。", "avg_price_per_person_cny": 700, "rating": 4.7, "location": {"lat": 39.9280, "lng": 116.4080}, "must_try_dishes": ["鹅肝", "龙虾汤", "巧克力苏芙蕾"]},
    {"name": "京兆尹", "area": "雍和宫", "cuisine": "素食", "description": "雍和宫旁的米其林三星素食餐厅，创意素食将食材做到极致，环境仙气飘飘。", "avg_price_per_person_cny": 600, "rating": 4.7, "location": {"lat": 39.9470, "lng": 116.4160}, "must_try_dishes": ["松茸汤", "菌菇拼盘", "桂花藕粉"]},
    {"name": "花厨", "area": "三里屯", "cuisine": "融合菜", "description": "少女心爆棚的花园餐厅，鲜花环绕，菜品颜值极高，是京城最适合闺蜜聚会和约会的餐厅。", "avg_price_per_person_cny": 200, "rating": 4.4, "location": {"lat": 39.9340, "lng": 116.4560}, "must_try_dishes": ["花厨沙拉", "玫瑰冰拿铁", "蜂蜜南瓜"]},

    # ── 异国/日韩 ──
    {"name": "慢走", "area": "三里屯", "cuisine": "日料", "description": "网红日式烧肉店，氛围轻松，牛舌和牛小排是必点，日式鸡尾酒也很出彩。", "avg_price_per_person_cny": 250, "rating": 4.4, "location": {"lat": 39.9335, "lng": 116.4580}, "must_try_dishes": ["厚切牛舌", "和牛小排", "抹茶冰淇淋"]},
    {"name": "望京一号", "area": "望京", "cuisine": "韩餐", "description": "望京最具人气的韩国料理，炸鸡和参鸡汤极其正宗，韩国人扎堆的店口味有保证。", "avg_price_per_person_cny": 100, "rating": 4.3, "location": {"lat": 39.9880, "lng": 116.4760}, "must_try_dishes": ["韩式炸鸡", "参鸡汤", "海鲜葱饼"]},
    {"name": "渔芙南", "area": "杨梅竹斜街", "cuisine": "湘菜", "description": "杨梅竹斜街里的文艺湘菜馆，剁椒鱼头辣得过瘾，胡同情调+火辣湘味的反差感。", "avg_price_per_person_cny": 120, "rating": 4.4, "location": {"lat": 39.8930, "lng": 116.3930}, "must_try_dishes": ["剁椒鱼头", "小炒黄牛肉", "擂辣椒皮蛋"]},
]

City = "上海"
SHANGHAI_RESTAURANTS = [
    # ── 本帮菜 ──
    {"name": "绿波廊", "area": "老城隍庙", "cuisine": "本帮菜", "description": "豫园内的国宴级本帮菜馆，接待过众多外国元首，招牌点心眉毛酥和桂花拉糕很有名。", "avg_price_per_person_cny": 250, "rating": 4.4, "location": {"lat": 31.2280, "lng": 121.4910}, "must_try_dishes": ["眉毛酥", "桂花拉糕", "八宝鸭"]},
    {"name": "上海老饭店", "area": "老城隍庙", "cuisine": "本帮菜", "description": "创建于1875年的本帮菜老字号，八宝辣酱和油爆河虾是经典中的经典，浓油赤酱的正宗味道。", "avg_price_per_person_cny": 180, "rating": 4.3, "location": {"lat": 31.2270, "lng": 121.4890}, "must_try_dishes": ["八宝辣酱", "油爆河虾", "扣三丝"]},
    {"name": "雍颐庭", "area": "陆家嘴", "cuisine": "本帮菜", "description": "浦东文华东方酒店内的米其林星级本帮菜，环境东方雅致，将传统本帮菜提升到新高度。", "avg_price_per_person_cny": 500, "rating": 4.7, "location": {"lat": 31.2410, "lng": 121.5080}, "must_try_dishes": ["红烧肉", "清炒河虾仁", "黄鱼面"]},

    # ── 生煎/小吃 ──
    {"name": "大壶春", "area": "云南南路", "cuisine": "小吃", "description": "上海最老牌的生煎馒头店，全发酵面皮、褶皱朝上煎，是上海生煎的另一大流派。", "avg_price_per_person_cny": 30, "rating": 4.3, "location": {"lat": 31.2240, "lng": 121.4810}, "must_try_dishes": ["鲜肉生煎", "虾仁生煎", "咖喱牛肉粉丝汤"]},
    {"name": "南翔馒头店", "area": "老城隍庙", "cuisine": "小吃", "description": "豫园九曲桥旁的小笼包名店，小笼包皮薄汤多，提褶精致，是上海的味觉名片。", "avg_price_per_person_cny": 80, "rating": 4.2, "location": {"lat": 31.2285, "lng": 121.4900}, "must_try_dishes": ["蟹粉小笼", "鲜肉小笼", "蛋皮汤"]},
    {"name": "德兴馆", "area": "广东路", "cuisine": "小吃", "description": "百年老字号面馆，焖蹄面和爆鱼面是上海面痴的最爱，汤头浓郁回味悠长。", "avg_price_per_person_cny": 40, "rating": 4.4, "location": {"lat": 31.2340, "lng": 121.4850}, "must_try_dishes": ["焖蹄面", "爆鱼面", "素鸡面"]},

    # ── 异国/西餐 ──
    {"name": "Ultraviolet by Paul Pairet", "area": "外滩", "cuisine": "前卫西餐", "description": "全球最前卫的餐厅体验之一，每晚只服务10位客人，沉浸式多感官用餐之旅，需提前数月预约。", "avg_price_per_person_cny": 6000, "rating": 4.9, "location": {"lat": 31.2400, "lng": 121.4920}, "must_try_dishes": ["感官套餐"]},
    {"name": "Mercato", "area": "外滩", "cuisine": "意大利菜", "description": "外滩6号的网红意大利餐厅，有机农场食材，黑松露pizza和牛肋排是明星菜品。", "avg_price_per_person_cny": 500, "rating": 4.6, "location": {"lat": 31.2405, "lng": 121.4925}, "must_try_dishes": ["黑松露披萨", "慢炖牛肋排", "提拉米苏"]},
    {"name": "Mr & Mrs Bund", "area": "外滩", "cuisine": "法餐", "description": "外滩18号的现代法餐，Paul Pairet主理，轻松氛围+顶级料理，橘子罐罐甜点是必吃。", "avg_price_per_person_cny": 600, "rating": 4.6, "location": {"lat": 31.2400, "lng": 121.4940}, "must_try_dishes": ["橘子罐罐", "黑松露薯条", "主厨特色海鲜塔"]},

    # ── 日料 ──
    {"name": "鮨一", "area": "古北", "cuisine": "日料", "description": "上海最顶级的江户前寿司店之一，每日从日本空运食材，师傅在吧台前逐一握制。", "avg_price_per_person_cny": 1500, "rating": 4.7, "location": {"lat": 31.2050, "lng": 121.3920}, "must_try_dishes": ["Omakase套餐", "金枪鱼大腹", "海胆寿司"]},
    {"name": "平成屋", "area": "新天地", "cuisine": "日料", "description": "日式居酒屋连锁，氛围如日剧般温馨，性价比高，烤串和炸鸡是招牌，下班后的人气去处。", "avg_price_per_person_cny": 120, "rating": 4.3, "location": {"lat": 31.2195, "lng": 121.4730}, "must_try_dishes": ["烤牛舌", "日式炸鸡", "梅酒"]},

    # ── 粤菜/点心 ──
    {"name": "唐宫", "area": "虹桥", "cuisine": "粤菜", "description": "上海老牌粤菜馆，乳鸽和虾饺是招牌，早茶点心种类丰富品质稳定。", "avg_price_per_person_cny": 180, "rating": 4.4, "location": {"lat": 31.2050, "lng": 121.4080}, "must_try_dishes": ["唐宫乳鸽", "虾饺皇", "杨枝甘露"]},
    {"name": "利苑", "area": "陆家嘴", "cuisine": "粤菜", "description": "ifc商场内的米其林星级粤菜馆，冰烧三层肉和鲍汁凤爪是经典，商务宴请和家庭聚餐佳选。", "avg_price_per_person_cny": 400, "rating": 4.5, "location": {"lat": 31.2365, "lng": 121.5050}, "must_try_dishes": ["冰烧三层肉", "鲍汁凤爪", "杨枝甘露"]},

    # ── 其他 ──
    {"name": "Maki House", "area": "静安寺", "cuisine": "日料", "description": "静安寺的网红日式蛋包饭店，流心蛋包饭切开瞬间爆浆，视觉和味觉的双重治愈。", "avg_price_per_person_cny": 100, "rating": 4.3, "location": {"lat": 31.2250, "lng": 121.4420}, "must_try_dishes": ["流心蛋包饭", "炸猪排", "抹茶拿铁"]},
    {"name": "蟹家大院", "area": "外滩", "cuisine": "本帮菜", "description": "专注大闸蟹的奢华面馆，一碗蟹黄面用12只大闸蟹的蟹黄蟹膏，金灿灿的一碗是上海人的顶级享受。", "avg_price_per_person_cny": 360, "rating": 4.5, "location": {"lat": 31.2390, "lng": 121.4915}, "must_try_dishes": ["蟹黄面", "醉蟹", "蟹肉面"]},
    {"name": "Farine", "area": "武康路", "cuisine": "面包甜点", "description": "武康路上的法式面包房，可颂和法棍是上海最佳之一，坐在梧桐树下的露台喝咖啡吃面包很惬意。", "avg_price_per_person_cny": 60, "rating": 4.4, "location": {"lat": 31.2070, "lng": 121.4380}, "must_try_dishes": ["杏仁可颂", "法棍", "巧克力面包"]},
]

City = "西安"
XIAN_RESTAURANTS = [
    # ── 陕菜/面食 ──
    {"name": "长安大牌档", "area": "钟楼", "cuisine": "陕菜", "description": "沉浸式唐风主题餐厅，内部仿唐代街市设计，有'店小二'古装服务和古琴表演，毛笔酥是网红。", "avg_price_per_person_cny": 100, "rating": 4.5, "location": {"lat": 34.2620, "lng": 108.9440}, "must_try_dishes": ["毛笔酥", "葫芦鸡", "麻将十三幺"]},
    {"name": "醉长安", "area": "南门", "cuisine": "陕菜", "description": "南门外的精品陕菜馆，妙笔生花和晾衣毛肚是招牌创意菜，环境古色古香。", "avg_price_per_person_cny": 120, "rating": 4.5, "location": {"lat": 34.2520, "lng": 108.9450}, "must_try_dishes": ["妙笔生花", "晾衣毛肚", "葫芦鸡"]},
    {"name": "西安饭庄", "area": "钟楼", "cuisine": "陕菜", "description": "西安餐饮界的中华老字号，创建于1929年，葫芦鸡和奶汤锅子鱼是陕菜正宗门面。", "avg_price_per_person_cny": 100, "rating": 4.3, "location": {"lat": 34.2615, "lng": 108.9445}, "must_try_dishes": ["葫芦鸡", "奶汤锅子鱼", "温拌腰丝"]},

    # ── 牛羊肉/泡馍 ──
    {"name": "同盛祥", "area": "钟楼", "cuisine": "泡馍", "description": "中华老字号羊肉泡馍馆，始创于1920年，汤浓肉烂馍入味，西安人眼中的泡馍天花板。", "avg_price_per_person_cny": 60, "rating": 4.4, "location": {"lat": 34.2610, "lng": 108.9440}, "must_try_dishes": ["羊肉泡馍", "腊牛肉夹馍", "麻酱凉皮"]},
    {"name": "老米家大雨肉夹馍", "area": "回民街", "cuisine": "小吃", "description": "回民街最有名的腊牛肉夹馍，肉量足、汁水多，排队是常态，但绝对值得等待。", "avg_price_per_person_cny": 30, "rating": 4.5, "location": {"lat": 34.2645, "lng": 108.9400}, "must_try_dishes": ["腊牛肉夹馍", "粉丝汤", "酸梅汤"]},
    {"name": "定家小酥肉", "area": "回民街", "cuisine": "小吃", "description": "回民街几十年的清真老店，炸过的牛肉蒸到软烂，油香肉香交融，配米饭是终极吃法。", "avg_price_per_person_cny": 35, "rating": 4.4, "location": {"lat": 34.2640, "lng": 108.9395}, "must_try_dishes": ["小酥肉", "米饭", "酸梅汤"]},
    {"name": "老刘家泡馍", "area": "回民街", "cuisine": "泡馍", "description": "回民街深处本地人常去的泡馍馆，环境朴实但味道一流，自己掰馍才是地道吃法。", "avg_price_per_person_cny": 40, "rating": 4.3, "location": {"lat": 34.2648, "lng": 108.9390}, "must_try_dishes": ["牛肉泡馍", "羊肉泡馍", "糖蒜"]},

    # ── 面食 ──
    {"name": "BiangBiang面馆", "area": "钟楼", "cuisine": "面食", "description": "西安BiangBiang面的代表店，面条宽如裤带，油泼辣子浇上去滋滋作响，视觉和味觉的双重冲击。", "avg_price_per_person_cny": 30, "rating": 4.4, "location": {"lat": 34.2605, "lng": 108.9430}, "must_try_dishes": ["BiangBiang面", "臊子面", "油泼面"]},
    {"name": "魏家凉皮", "area": "钟楼", "cuisine": "小吃", "description": "西安凉皮连锁品牌，秘制凉皮酸辣爽口，是西安人夏天消暑标配。", "avg_price_per_person_cny": 25, "rating": 4.2, "location": {"lat": 34.2610, "lng": 108.9425}, "must_try_dishes": ["秘制凉皮", "肉夹馍", "冰峰汽水"]},
    {"name": "柳巷面馆", "area": "东大街", "cuisine": "面食", "description": "西安几十年的老面馆，主打牛肉面，面条筋道汤头浓郁，一碗面配一瓶冰峰是西安人的乡愁。", "avg_price_per_person_cny": 25, "rating": 4.4, "location": {"lat": 34.2600, "lng": 108.9550}, "must_try_dishes": ["牛肉面", "油泼面", "冰峰"]},

    # ── 烤串/夜市 ──
    {"name": "马乐烤肉", "area": "回民街", "cuisine": "烧烤", "description": "回民街最有名的清真烤肉，羊肉串用红柳枝串烤，肉香中透着红柳清香。", "avg_price_per_person_cny": 60, "rating": 4.4, "location": {"lat": 34.2642, "lng": 108.9385}, "must_try_dishes": ["红柳烤肉", "烤羊腰", "馕"]},
    {"name": "小骆驼烧烤", "area": "大唐不夜城", "cuisine": "烧烤", "description": "大雁塔附近的网红烧烤店，开放式厨房现烤现吃，羊肉串和烤茄子是标杆。", "avg_price_per_person_cny": 80, "rating": 4.3, "location": {"lat": 34.2170, "lng": 108.9620}, "must_try_dishes": ["羊肉串", "烤茄子", "蒜蓉烤饼"]},

    # ── 饺子/其他 ──
    {"name": "德发长饺子馆", "area": "钟楼", "cuisine": "饺子", "description": "中华老字号，饺子宴驰名中外，将饺子做成各种造型和口味，一饺一形百饺百味。", "avg_price_per_person_cny": 120, "rating": 4.3, "location": {"lat": 34.2615, "lng": 108.9430}, "must_try_dishes": ["饺子宴", "太后火锅饺", "酸汤水饺"]},
    {"name": "春发生", "area": "南院门", "cuisine": "陕菜", "description": "西安葫芦头泡馍的百年老字号，猪大肠处理得干净无异味，汤头鲜美浓郁。", "avg_price_per_person_cny": 50, "rating": 4.3, "location": {"lat": 34.2600, "lng": 108.9400}, "must_try_dishes": ["葫芦头泡馍", "梆梆肉", "熏大肠"]},
    {"name": "贾三灌汤包", "area": "回民街", "cuisine": "小吃", "description": "回民街必打卡的清真灌汤包，牛羊肉灌汤包皮薄汤多，先开窗后喝汤是标准吃法。", "avg_price_per_person_cny": 40, "rating": 4.2, "location": {"lat": 34.2643, "lng": 108.9405}, "must_try_dishes": ["牛肉灌汤包", "羊肉灌汤包", "八宝粥"]},
    {"name": "舍外", "area": "雁塔区", "cuisine": "融合菜", "description": "大雁塔附近的网红融合餐厅，将陕菜与现代料理融合，环境设计感强，适合拍照打卡。", "avg_price_per_person_cny": 150, "rating": 4.3, "location": {"lat": 34.2150, "lng": 108.9650}, "must_try_dishes": ["创意葫芦鸡", "分子水果拼盘", "抹茶甜品"]},
    {"name": "海底捞火锅西安老城根店", "area": "老城根", "cuisine": "火锅", "description": "全国知名的服务标杆火锅店，等位时有美甲擦鞋小吃服务，海底捞式体验从西安走向全国。", "avg_price_per_person_cny": 130, "rating": 4.6, "location": {"lat": 34.2700, "lng": 108.9350}, "must_try_dishes": ["捞派毛肚", "虾滑", "番茄锅底"]},
]

ALL_RESTAURANTS = {
    "成都": CHENGDU_RESTAURANTS,
    "北京": BEIJING_RESTAURANTS,
    "上海": SHANGHAI_RESTAURANTS,
    "西安": XIAN_RESTAURANTS,
}


def seed_city(city: str):
    restaurants = ALL_RESTAURANTS.get(city, [])
    if not restaurants:
        print(f"No restaurant data for {city}")
        return 0

    store = get_chroma_store()
    existing = store.search_restaurants(city, city=city, k=1)
    if existing:
        print(f"{city} restaurant data already exists. Delete first if re-seed.")
        return 0

    for r in restaurants:
        r["city"] = city

    n = store.add_restaurants(restaurants)
    print(f"Seeded {n} restaurants for {city}")
    return n


def seed():
    total = 0
    for city in ALL_RESTAURANTS:
        n = seed_city(city)
        total += n
    store = get_chroma_store()
    print(f"\nTotal restaurants in ChromaDB: {store.collection_count('restaurants')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed restaurants into ChromaDB")
    parser.add_argument("city", nargs="?", default="all", choices=list(ALL_RESTAURANTS.keys()) + ["all"])
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    if args.clear:
        get_chroma_store().delete_collection("restaurants")

    if args.city == "all":
        seed()
    else:
        seed_city(args.city)
