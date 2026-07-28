"""Seed hotels into ChromaDB for semantic search. Covers Chengdu, Beijing, Shanghai, Xi'an."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

City = "成都"
CHENGDU_HOTELS = [
    # ── 春熙路/太古里商圈 ──
    {"name": "成都尼依格罗酒店", "area": "春熙路", "description": "IFS国际金融中心顶层的奢华酒店，客房可俯瞰太古里全景，设计现代简约，服务一流。", "price_per_night_cny": 1500, "rating": 4.7, "location": {"lat": 30.6545, "lng": 104.0843}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅", "酒吧"]},
    {"name": "成都博舍酒店", "area": "太古里", "description": "太古里内的精品酒店，由百年历史建筑改建，融合川西庭院与现代设计，是成都最有格调的酒店之一。", "price_per_night_cny": 1800, "rating": 4.8, "location": {"lat": 30.6530, "lng": 104.0835}, "amenities": ["WiFi", "花园", "健身房", "餐厅", "酒吧"]},
    {"name": "成都群光君悦酒店", "area": "春熙路", "description": "春熙路核心地段的五星级酒店，法式风情设计，房间宽敞，早餐丰盛。", "price_per_night_cny": 900, "rating": 4.6, "location": {"lat": 30.6570, "lng": 104.0810}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅"]},
    {"name": "成都太古里宜必思酒店", "area": "春熙路", "description": "经济型连锁酒店，位置绝佳，步行可达太古里和春熙路，性价比极高。", "price_per_night_cny": 250, "rating": 4.1, "location": {"lat": 30.6560, "lng": 104.0790}, "amenities": ["WiFi", "洗衣"]},
    {"name": "如家精选成都春熙路店", "area": "春熙路", "description": "连锁中端酒店，干净整洁，紧邻春熙路地铁站，适合预算有限的自由行游客。", "price_per_night_cny": 300, "rating": 4.2, "location": {"lat": 30.6585, "lng": 104.0780}, "amenities": ["WiFi", "洗衣"]},

    # ── 宽窄巷子/人民公园 ──
    {"name": "成都钓鱼台精品酒店", "area": "宽窄巷子", "description": "宽窄巷子内的顶级精品酒店，由清代庭院改建，每间客房都是独一无二的艺术品。", "price_per_night_cny": 2200, "rating": 4.8, "location": {"lat": 30.6750, "lng": 104.0530}, "amenities": ["WiFi", "花园", "餐厅", "管家服务"]},
    {"name": "成都天府丽都喜来登酒店", "area": "天府广场", "description": "天府广场旁的五星级商务酒店，交通便利，房间舒适，服务专业。", "price_per_night_cny": 700, "rating": 4.4, "location": {"lat": 30.6590, "lng": 104.0640}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅"]},
    {"name": "成都宽窄巷子亚朵酒店", "area": "宽窄巷子", "description": "以阅读和人文为主题的精品酒店，毗邻宽窄巷子，设计有成都文化特色，竹叶元素贯穿始终。", "price_per_night_cny": 450, "rating": 4.5, "location": {"lat": 30.6730, "lng": 104.0550}, "amenities": ["WiFi", "书吧", "健身房", "洗衣"]},
    {"name": "成都蓝城悦榕庄", "area": "锦里", "description": "锦里古街附近的温泉度假酒店，中式禅意设计，有温泉泡池和庭院茶室。", "price_per_night_cny": 1200, "rating": 4.7, "location": {"lat": 30.6420, "lng": 104.0450}, "amenities": ["WiFi", "温泉", "花园", "餐厅", "茶室"]},
    {"name": "成都锦里亚朵酒店", "area": "锦里", "description": "武侯祠锦里附近的人文中端酒店，出行方便，早餐有成都特色小吃。", "price_per_night_cny": 420, "rating": 4.4, "location": {"lat": 30.6440, "lng": 104.0470}, "amenities": ["WiFi", "书吧", "洗衣"]},

    # ── 高新/南门 ──
    {"name": "成都华尔道夫酒店", "area": "高新区", "description": "成都南门的地标性奢华酒店，高空大堂可俯瞰城市天际线，下午茶和酒吧是网红打卡点。", "price_per_night_cny": 1600, "rating": 4.8, "location": {"lat": 30.5800, "lng": 104.0670}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅", "酒吧"]},
    {"name": "成都世纪城天堂洲际酒店", "area": "高新区", "description": "世纪城会展中心旁的五星级酒店，有室内热带花园和大型泳池，适合商务和度假。", "price_per_night_cny": 800, "rating": 4.5, "location": {"lat": 30.5570, "lng": 104.0730}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅", "花园"]},
    {"name": "成都希尔顿酒店", "area": "高新区", "description": "天府大道旁的现代五星级酒店，高层客房视野开阔，自助餐品质出众。", "price_per_night_cny": 750, "rating": 4.5, "location": {"lat": 30.5750, "lng": 104.0650}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅"]},
    {"name": "成都凯悦嘉轩酒店", "area": "高新区", "description": "象南里商圈的中高端酒店，设计时尚，适合年轻商务客和游客。", "price_per_night_cny": 550, "rating": 4.4, "location": {"lat": 30.5850, "lng": 104.0600}, "amenities": ["WiFi", "健身房", "餐厅"]},
    {"name": "成都全季酒店天府三街店", "area": "高新区", "description": "华住旗下中端酒店，东方简约风，设施新，靠近地铁站，商务出行优选。", "price_per_night_cny": 350, "rating": 4.3, "location": {"lat": 30.5600, "lng": 104.0580}, "amenities": ["WiFi", "洗衣"]},

    # ── 东郊/理工 ──
    {"name": "成都东郊记忆亚朵酒店", "area": "东郊记忆", "description": "东郊记忆文创园区附近的人文化酒店，工业风设计，周边有众多网红咖啡馆和餐厅。", "price_per_night_cny": 420, "rating": 4.4, "location": {"lat": 30.6650, "lng": 104.1250}, "amenities": ["WiFi", "书吧", "健身房"]},
    {"name": "成都理工大学希尔顿欢朋酒店", "area": "成华区", "description": "成都东门的中高端酒店，靠近成都理工大学和东郊记忆，性价比高。", "price_per_night_cny": 480, "rating": 4.3, "location": {"lat": 30.6700, "lng": 104.1350}, "amenities": ["WiFi", "健身房", "餐厅"]},

    # ── 都江堰/青城山 ──
    {"name": "青城山六善酒店", "area": "青城山", "description": "青城山脚下的顶级度假酒店，融入道家文化理念，有机农场到餐桌的餐饮体验，静修首选。", "price_per_night_cny": 3000, "rating": 4.9, "location": {"lat": 30.8960, "lng": 103.5700}, "amenities": ["WiFi", "泳池", "SPA", "花园", "餐厅", "农场"]},
    {"name": "都江堰安缇缦度假酒店", "area": "都江堰", "description": "都江堰景区的禅意度假酒店，被竹林环抱，有温泉和太极课程，适合养生度假。", "price_per_night_cny": 1300, "rating": 4.6, "location": {"lat": 30.9880, "lng": 103.6180}, "amenities": ["WiFi", "温泉", "SPA", "花园", "餐厅"]},

    # ── 经济型 ──
    {"name": "汉庭酒店成都天府广场店", "area": "天府广场", "description": "市中心的经济型连锁酒店，位置便利，价格实惠，基本设施齐全。", "price_per_night_cny": 220, "rating": 4.0, "location": {"lat": 30.6600, "lng": 104.0660}, "amenities": ["WiFi"]},
]

City = "北京"
BEIJING_HOTELS = [
    # ── 王府井/故宫 ──
    {"name": "北京王府半岛酒店", "area": "王府井", "description": "王府井核心区的顶级奢华酒店，中西合璧设计，屋顶餐厅可眺望故宫，服务无可挑剔。", "price_per_night_cny": 2500, "rating": 4.8, "location": {"lat": 39.9140, "lng": 116.4110}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "管家服务"]},
    {"name": "北京华尔道夫酒店", "area": "王府井", "description": "金鱼胡同的奢华酒店，黄铜外观引人注目，客房配备顶级设施，下午茶享誉京城。", "price_per_night_cny": 2200, "rating": 4.8, "location": {"lat": 39.9155, "lng": 116.4130}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧"]},
    {"name": "北京璞瑄酒店", "area": "王府井", "description": "嘉德艺术中心上层的设计酒店，紧邻故宫和景山，现代东方美学，部分客房可看故宫。", "price_per_night_cny": 2000, "rating": 4.7, "location": {"lat": 39.9200, "lng": 116.4080}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "餐厅"]},
    {"name": "北京王府井希尔顿酒店", "area": "王府井", "description": "王府井步行街附近的五星级商务酒店，位置极佳，步行可达故宫和天安门。", "price_per_night_cny": 1000, "rating": 4.5, "location": {"lat": 39.9130, "lng": 116.4140}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅"]},
    {"name": "北京如家精选故宫店", "area": "东华门", "description": "故宫东华门附近的经济型酒店，位置绝佳，步行可达故宫午门，背包客首选。", "price_per_night_cny": 350, "rating": 4.1, "location": {"lat": 39.9150, "lng": 116.4030}, "amenities": ["WiFi", "洗衣"]},

    # ── 后海/南锣鼓巷 ──
    {"name": "北京什刹海四合院酒店", "area": "后海", "description": "后海胡同里的精品四合院酒店，保留了传统北京民居格局，可在院中喝茶体验老北京生活。", "price_per_night_cny": 1200, "rating": 4.7, "location": {"lat": 39.9370, "lng": 116.3840}, "amenities": ["WiFi", "花园", "茶室", "早餐"]},
    {"name": "北京南锣鼓巷citizenM酒店", "area": "南锣鼓巷", "description": "南锣鼓巷附近的设计酒店，荷兰品牌，智能客房控制系统，屋顶酒吧可看鼓楼。", "price_per_night_cny": 680, "rating": 4.5, "location": {"lat": 39.9410, "lng": 116.4030}, "amenities": ["WiFi", "酒吧", "餐厅"]},
    {"name": "北京花间堂后海店", "area": "后海", "description": "毗邻后海的小型精品酒店，设计融入羊房胡同文化，屋顶露台可眺望什刹海。", "price_per_night_cny": 850, "rating": 4.6, "location": {"lat": 39.9385, "lng": 116.3850}, "amenities": ["WiFi", "露台", "花园", "餐厅"]},

    # ── 三里屯/国贸 ──
    {"name": "北京宝格丽酒店", "area": "三里屯", "description": "亮马河畔的顶级奢华酒店，意大利珠宝品牌Bvlgari的东方之作，花园和河景令人惊艳。", "price_per_night_cny": 3500, "rating": 4.9, "location": {"lat": 39.9360, "lng": 116.4620}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "花园", "餐厅", "管家服务"]},
    {"name": "北京三里屯洲际酒店", "area": "三里屯", "description": "三里屯太古里对面的五星级酒店，设计前卫，紧邻酒吧街和潮流商圈，适合时尚人群。", "price_per_night_cny": 1300, "rating": 4.6, "location": {"lat": 39.9330, "lng": 116.4550}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅", "酒吧"]},
    {"name": "北京瑜舍酒店", "area": "三里屯", "description": "太古里内的日式极简设计酒店，隈研吾设计，房间超大，闹中取静的艺术空间。", "price_per_night_cny": 1800, "rating": 4.7, "location": {"lat": 39.9320, "lng": 116.4540}, "amenities": ["WiFi", "泳池", "健身房", "餐厅"]},
    {"name": "北京国贸大酒店", "area": "国贸", "description": "国贸三期大厦高层，北京最高的酒店之一，空中大堂俯瞰CBD全景，商务奢华标杆。", "price_per_night_cny": 1800, "rating": 4.7, "location": {"lat": 39.9090, "lng": 116.4600}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧"]},
    {"name": "北京三里屯CHAO酒店", "area": "三里屯", "description": "设计感极强的精品酒店，大量艺术装置和展览空间，B1层的大型休闲区是京城潮人聚集地。", "price_per_night_cny": 1100, "rating": 4.5, "location": {"lat": 39.9350, "lng": 116.4570}, "amenities": ["WiFi", "健身房", "餐厅", "酒吧"]},

    # ── 颐和园/海淀 ──
    {"name": "北京颐和安缦", "area": "颐和园", "description": "颐和园东门旁的顶级度假酒店，由清代皇家四合院改建，有私人通道直入颐和园。", "price_per_night_cny": 4500, "rating": 4.9, "location": {"lat": 39.9970, "lng": 116.2780}, "amenities": ["WiFi", "泳池", "SPA", "花园", "餐厅", "管家服务"]},
    {"name": "北京香格里拉饭店", "area": "紫竹院", "description": "海淀区的老牌五星级酒店，花园式设计，毗邻紫竹院公园，适合商务和观光。", "price_per_night_cny": 800, "rating": 4.4, "location": {"lat": 39.9460, "lng": 116.3190}, "amenities": ["WiFi", "泳池", "健身房", "花园", "停车", "餐厅"]},

    # ── 鼓楼/雍和宫 ──
    {"name": "北京鼓楼亚朵酒店", "area": "鼓楼", "description": "鼓楼东大街的人文酒店，步行可达南锣鼓巷和什刹海，设计有老北京元素。", "price_per_night_cny": 500, "rating": 4.4, "location": {"lat": 39.9430, "lng": 116.3950}, "amenities": ["WiFi", "书吧", "洗衣"]},
    {"name": "北京速8雍和宫店", "area": "雍和宫", "description": "雍和宫地铁站旁的经济型酒店，交通便利，性价比高，适合背包客。", "price_per_night_cny": 260, "rating": 3.9, "location": {"lat": 39.9480, "lng": 116.4180}, "amenities": ["WiFi"]},

    # ── 前门/大栅栏 ──
    {"name": "北京前门漫心酒店", "area": "前门", "description": "前门大栅栏胡同里的精品酒店，由老北京民居改造，出门即是老字号店铺和茶馆。", "price_per_night_cny": 550, "rating": 4.5, "location": {"lat": 39.8960, "lng": 116.3970}, "amenities": ["WiFi", "花园", "茶室"]},
]

City = "上海"
SHANGHAI_HOTELS = [
    # ── 外滩/南京路 ──
    {"name": "上海半岛酒店", "area": "外滩", "description": "外滩源头的顶级酒店，直面黄浦江，装饰艺术风格，米其林餐厅和屋顶酒吧享誉沪上。", "price_per_night_cny": 2800, "rating": 4.9, "location": {"lat": 31.2430, "lng": 121.4890}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧", "管家服务"]},
    {"name": "上海和平饭店", "area": "外滩", "description": "外滩历史地标酒店，Art Deco装饰风格，老年爵士乐队闻名世界，住在这里就是住进历史。", "price_per_night_cny": 2000, "rating": 4.7, "location": {"lat": 31.2410, "lng": 121.4905}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "爵士酒吧"]},
    {"name": "上海外滩华尔道夫酒店", "area": "外滩", "description": "外滩万国建筑群中的奢华酒店，新楼与老楼相连，老楼的廊吧是外滩经典。", "price_per_night_cny": 2200, "rating": 4.8, "location": {"lat": 31.2380, "lng": 121.4910}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧"]},
    {"name": "上海外滩茂悦大酒店", "area": "外滩", "description": "外滩北端的高层五星级酒店，VUE Bar的露台是无遮挡的外滩三件套最佳观赏点。", "price_per_night_cny": 1200, "rating": 4.6, "location": {"lat": 31.2470, "lng": 121.4920}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅", "酒吧"]},
    {"name": "上海南京路步行街假日酒店", "area": "南京路", "description": "南京路步行街旁的中端酒店，购物出行极为便利，性价比高。", "price_per_night_cny": 550, "rating": 4.3, "location": {"lat": 31.2360, "lng": 121.4760}, "amenities": ["WiFi", "健身房"]},

    # ── 陆家嘴/浦东 ──
    {"name": "上海浦东丽思卡尔顿酒店", "area": "陆家嘴", "description": "国金中心顶部的奢华酒店，客房可俯瞰黄浦江和外滩天际线，Flair顶层酒吧是陆家嘴地标。", "price_per_night_cny": 2500, "rating": 4.8, "location": {"lat": 31.2370, "lng": 121.5040}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧"]},
    {"name": "上海柏悦酒店", "area": "陆家嘴", "description": "环球金融中心79-93层的超高空酒店，上海最高的客房之一，极简日式奢华风格。", "price_per_night_cny": 2000, "rating": 4.7, "location": {"lat": 31.2370, "lng": 121.5055}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "上海浦东香格里拉酒店", "area": "陆家嘴", "description": "陆家嘴核心的老牌奢华酒店，紧邻滨江大道，正大广场购物方便，江景房直面外滩。", "price_per_night_cny": 1300, "rating": 4.6, "location": {"lat": 31.2390, "lng": 121.5020}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "上海陆家嘴亚朵酒店", "area": "陆家嘴", "description": "陆家嘴商圈的人文中端酒店，价格相对合理，商务出行和观光都很方便。", "price_per_night_cny": 600, "rating": 4.4, "location": {"lat": 31.2320, "lng": 121.5100}, "amenities": ["WiFi", "书吧", "健身房", "洗衣"]},

    # ── 新天地/法租界 ──
    {"name": "上海安达仕酒店", "area": "新天地", "description": "新天地旁的时尚奢华酒店，凯悦旗下，设计充满艺术感，紧邻石库门建筑群。", "price_per_night_cny": 1400, "rating": 4.6, "location": {"lat": 31.2190, "lng": 121.4750}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "上海新天地朗廷酒店", "area": "新天地", "description": "新天地核心位置的英伦风奢华酒店，粉色出租车是标志，下午茶和川SPA口碑极佳。", "price_per_night_cny": 1500, "rating": 4.7, "location": {"lat": 31.2180, "lng": 121.4740}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "上海花园饭店", "area": "淮海路", "description": "原法国俱乐部旧址，拥有市中心难得的大花园，建筑融合法式和Art Deco风格。", "price_per_night_cny": 900, "rating": 4.5, "location": {"lat": 31.2210, "lng": 121.4660}, "amenities": ["WiFi", "泳池", "健身房", "花园", "停车", "餐厅"]},
    {"name": "上海思南公馆酒店", "area": "思南路", "description": "思南路上的花园洋房酒店，由法租界时期的老洋房改建，梧桐树下最上海的风情。", "price_per_night_cny": 1600, "rating": 4.6, "location": {"lat": 31.2150, "lng": 121.4680}, "amenities": ["WiFi", "花园", "餐厅", "洋房"]},

    # ── 静安寺/南京西路 ──
    {"name": "上海素凯泰酒店", "area": "静安寺", "description": "静安寺旁的泰式奢华酒店，URBAN Café和La Scala餐厅获米其林推荐，设计极简禅意。", "price_per_night_cny": 1600, "rating": 4.7, "location": {"lat": 31.2260, "lng": 121.4440}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "上海静安瑞吉酒店", "area": "静安寺", "description": "静安区核心的奢华酒店，瑞吉品牌标志性的管家服务，瑞吉酒吧的Bloody Mary闻名沪上。", "price_per_night_cny": 1700, "rating": 4.7, "location": {"lat": 31.2270, "lng": 121.4480}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧", "管家服务"]},
    {"name": "上海静安香格里拉", "area": "静安寺", "description": "静安嘉里中心上方的五星级酒店，两咖啡自助餐品类丰富，1515牛排馆是沪上最佳牛排之一。", "price_per_night_cny": 1400, "rating": 4.6, "location": {"lat": 31.2250, "lng": 121.4460}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},

    # ── 迪士尼 ──
    {"name": "上海迪士尼乐园酒店", "area": "迪士尼", "description": "迪士尼度假区内的主题酒店，维多利亚风格，有米奇元素客房和花园，可乘船或巴士去乐园。", "price_per_night_cny": 2000, "rating": 4.6, "location": {"lat": 31.1420, "lng": 121.6580}, "amenities": ["WiFi", "泳池", "花园", "停车", "餐厅", "儿童俱乐部"]},
    {"name": "上海玩具总动员酒店", "area": "迪士尼", "description": "迪士尼度假区内性价比更高的主题酒店，以玩具总动员为主题，色彩明亮，适合亲子家庭。", "price_per_night_cny": 1200, "rating": 4.4, "location": {"lat": 31.1410, "lng": 121.6560}, "amenities": ["WiFi", "花园", "停车", "餐厅", "儿童俱乐部"]},
]

City = "西安"
XIAN_HOTELS = [
    # ── 钟楼/回民街 ──
    {"name": "西安索菲特传奇酒店", "area": "钟楼", "description": "原人民大厦改建的传奇级酒店，1950年代建筑融合法式优雅，花园和泳池在西安独一无二。", "price_per_night_cny": 1500, "rating": 4.8, "location": {"lat": 34.2620, "lng": 108.9460}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "花园", "停车", "餐厅"]},
    {"name": "西安钟楼饭店", "area": "钟楼", "description": "钟楼旁的地标酒店，紧邻钟鼓楼和回民街，位置无可比拟，住在这里就是住在西安的中心。", "price_per_night_cny": 600, "rating": 4.3, "location": {"lat": 34.2610, "lng": 108.9435}, "amenities": ["WiFi", "停车", "餐厅"]},
    {"name": "西安美丽豪酒店钟楼店", "area": "钟楼", "description": "钟楼商圈的中高端酒店，距回民街步行仅5分钟，大堂有西安历史文化展示。", "price_per_night_cny": 450, "rating": 4.4, "location": {"lat": 34.2625, "lng": 108.9420}, "amenities": ["WiFi", "健身房"]},
    {"name": "西安回民街亚朵酒店", "area": "回民街", "description": "回民街附近的人文酒店，设计融入唐文化和丝路元素，出门即可品尝各色小吃。", "price_per_night_cny": 420, "rating": 4.4, "location": {"lat": 34.2640, "lng": 108.9410}, "amenities": ["WiFi", "书吧", "洗衣"]},

    # ── 大雁塔/曲江 ──
    {"name": "西安W酒店", "area": "曲江", "description": "曲江池畔的潮流奢华酒店，设计前卫，融合唐文化元素与现代时尚，无边泳池可看大雁塔。", "price_per_night_cny": 1600, "rating": 4.7, "location": {"lat": 34.2050, "lng": 108.9680}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅", "酒吧"]},
    {"name": "西安威斯汀大酒店", "area": "大雁塔", "description": "大雁塔南广场对面的五星级酒店，部分客房可看大雁塔音乐喷泉，地下有唐代艺术博物馆。", "price_per_night_cny": 900, "rating": 4.5, "location": {"lat": 34.2160, "lng": 108.9630}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "西安凯悦酒店", "area": "曲江", "description": "曲江池遗址公园旁的度假型五星级酒店，园林设计大气，适合家庭度假。", "price_per_night_cny": 850, "rating": 4.6, "location": {"lat": 34.2080, "lng": 108.9750}, "amenities": ["WiFi", "泳池", "健身房", "花园", "停车", "餐厅"]},
    {"name": "西安大雁塔亚朵酒店", "area": "大雁塔", "description": "大雁塔景区附近的人文中端酒店，步行可达大唐不夜城，夜游方便。", "price_per_night_cny": 450, "rating": 4.4, "location": {"lat": 34.2180, "lng": 108.9600}, "amenities": ["WiFi", "书吧", "洗衣"]},

    # ── 曲江新区 ──
    {"name": "西安盛美利亚酒店", "area": "曲江", "description": "西班牙品牌在西安的奢华酒店，融合盛唐建筑风格，紧邻大唐芙蓉园。", "price_per_night_cny": 1000, "rating": 4.6, "location": {"lat": 34.2130, "lng": 108.9720}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},

    # ── 城墙内/南门 ──
    {"name": "西安君乐城堡酒店", "area": "南门", "description": "南门广场旁的五星级酒店，紧邻古城墙，可上城墙骑行，古城与现代的完美结合。", "price_per_night_cny": 700, "rating": 4.4, "location": {"lat": 34.2530, "lng": 108.9460}, "amenities": ["WiFi", "泳池", "健身房", "停车", "餐厅"]},
    {"name": "西安南门亚朵酒店", "area": "南门", "description": "南门外的人文中端酒店，靠近SKP和城墙景区，交通便利。", "price_per_night_cny": 430, "rating": 4.3, "location": {"lat": 34.2510, "lng": 108.9470}, "amenities": ["WiFi", "书吧", "洗衣"]},

    # ── 兵马俑/临潼 ──
    {"name": "西安临潼悦椿温泉酒店", "area": "临潼", "description": "骊山脚下的温泉度假酒店，毗邻兵马俑博物馆，有大型温泉浴场和SPA。", "price_per_night_cny": 1100, "rating": 4.6, "location": {"lat": 34.3800, "lng": 109.2700}, "amenities": ["WiFi", "温泉", "泳池", "SPA", "花园", "停车", "餐厅"]},
    {"name": "西安华清御汤酒店", "area": "临潼", "description": "华清池景区内的温泉酒店，可泡杨贵妃同款骊山温泉，房间是唐风庭院别墅。", "price_per_night_cny": 1800, "rating": 4.7, "location": {"lat": 34.3650, "lng": 109.2100}, "amenities": ["WiFi", "温泉", "SPA", "花园", "停车", "餐厅"]},

    # ── 高新 ──
    {"name": "西安丽思卡尔顿酒店", "area": "高新区", "description": "西安高新区的顶级商务奢华酒店，设计融入丝路文化，自助餐品类西安最佳之一。", "price_per_night_cny": 1400, "rating": 4.7, "location": {"lat": 34.2330, "lng": 108.8950}, "amenities": ["WiFi", "泳池", "健身房", "SPA", "停车", "餐厅"]},
    {"name": "西安高新区全季酒店", "area": "高新区", "description": "高新区的经济型中端酒店，东方简约风格，商务出差实惠之选。", "price_per_night_cny": 320, "rating": 4.2, "location": {"lat": 34.2300, "lng": 108.8900}, "amenities": ["WiFi", "洗衣"]},
    {"name": "西安大唐西市亚朵酒店", "area": "大唐西市", "description": "大唐西市商圈的人文化酒店，丝路主题设计，周边有博物馆和大唐西市遗址。", "price_per_night_cny": 400, "rating": 4.3, "location": {"lat": 34.2560, "lng": 108.9100}, "amenities": ["WiFi", "书吧", "健身房"]},
]

ALL_HOTELS = {
    "成都": CHENGDU_HOTELS,
    "北京": BEIJING_HOTELS,
    "上海": SHANGHAI_HOTELS,
    "西安": XIAN_HOTELS,
}


def seed_city(city: str):
    hotels = ALL_HOTELS.get(city, [])
    if not hotels:
        print(f"No hotel data for {city}")
        return 0

    store = get_chroma_store()
    existing = store.search_hotels(city, city=city, k=1)
    if existing:
        print(f"{city} hotel data already exists. Delete first if re-seed.")
        return 0

    for h in hotels:
        h["city"] = city

    n = store.add_hotels(hotels)
    print(f"Seeded {n} hotels for {city}")
    return n


def seed():
    total = 0
    for city in ALL_HOTELS:
        n = seed_city(city)
        total += n
    store = get_chroma_store()
    print(f"\nTotal hotels in ChromaDB: {store.collection_count('hotels')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed hotels into ChromaDB")
    parser.add_argument("city", nargs="?", default="all", choices=list(ALL_HOTELS.keys()) + ["all"])
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    if args.clear:
        get_chroma_store().delete_collection("hotels")

    if args.city == "all":
        seed()
    else:
        seed_city(args.city)
