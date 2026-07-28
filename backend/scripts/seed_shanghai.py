"""Seed Shanghai attractions into ChromaDB for semantic search."""

import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_shanghai
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

SHANGHAI_ATTRACTIONS = [
    {"name": "外滩", "category": "cultural", "description": "上海最具标志性的景观，黄浦江西岸的万国建筑博览群与对岸陆家嘴摩天大楼交相辉映，夜景尤为壮观。", "rating": 4.8, "ticket_price_cny": 0, "location": {"lat": 31.2400, "lng": 121.4904}, "tags": ["城市地标", "夜景", "建筑", "拍照"], "suitable_for": ["家庭", "情侣", "独行", "老人"], "opening_hours": "全天"},
    {"name": "豫园", "category": "cultural", "description": "始建于明代的江南古典园林，亭台楼阁、假山池塘精巧别致，是上海市中心难得的园林瑰宝。", "rating": 4.6, "ticket_price_cny": 40, "location": {"lat": 31.2272, "lng": 121.4924}, "tags": ["古典园林", "历史文化", "建筑", "拍照"], "suitable_for": ["家庭", "情侣", "老人", "独行"], "opening_hours": "08:30-17:30"},
    {"name": "城隍庙", "category": "cultural", "description": "上海最负盛名的道教宫观，始建于明永乐年间，香火鼎盛，周边是热闹的城隍庙小吃和购物区。", "rating": 4.4, "ticket_price_cny": 10, "location": {"lat": 31.2269, "lng": 121.4916}, "tags": ["道教文化", "历史", "美食", "购物"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "08:30-16:30"},
    {"name": "静安寺", "category": "cultural", "description": "上海最古老的佛教寺庙之一，始建于三国时期，金碧辉煌的寺塔矗立在繁华商圈中央，形成独特景观。", "rating": 4.5, "ticket_price_cny": 50, "location": {"lat": 31.2231, "lng": 121.4486}, "tags": ["佛教文化", "历史", "建筑", "城市地标"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "07:30-17:00"},
    {"name": "龙华寺", "category": "cultural", "description": "上海历史最悠久、规模最大的佛教寺院，以龙华塔和龙华桃花闻名，每年新春撞钟祈福吸引众多信众。", "rating": 4.4, "ticket_price_cny": 10, "location": {"lat": 31.1756, "lng": 121.4518}, "tags": ["佛教文化", "历史", "古塔", "祈福"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "07:00-17:00"},
    {"name": "玉佛寺", "category": "cultural", "description": "因供奉两尊缅甸请来的玉佛而得名，玉佛洁白无瑕、雕工精湛，是上海佛教名刹之一。", "rating": 4.3, "ticket_price_cny": 20, "location": {"lat": 31.2410, "lng": 121.4403}, "tags": ["佛教文化", "历史", "文物"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-16:30"},
    {"name": "上海博物馆", "category": "cultural", "description": "中国最著名的博物馆之一，以青铜器、陶瓷、书法、绘画等馆藏闻名中外，建筑设计取'天圆地方'之意。", "rating": 4.7, "ticket_price_cny": 0, "location": {"lat": 31.2304, "lng": 121.4737}, "tags": ["博物馆", "历史文化", "文物", "艺术", "免费"], "suitable_for": ["家庭", "老人", "独行", "儿童"], "opening_hours": "09:00-17:00"},
    {"name": "中华艺术宫", "category": "cultural", "description": "由2010年上海世博会中国馆改造而成的国家级艺术博物馆，动态版《清明上河图》是镇馆之宝。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.1866, "lng": 121.4806}, "tags": ["博物馆", "艺术", "世博", "建筑", "免费"], "suitable_for": ["家庭", "老人", "独行", "儿童"], "opening_hours": "10:00-18:00"},
    {"name": "上海科技馆", "category": "cultural", "description": "以'自然·人·科技'为主题的大型科普场馆，有互动展项和IMAX影院，是寓教于乐的好去处。", "rating": 4.5, "ticket_price_cny": 45, "location": {"lat": 31.2205, "lng": 121.5410}, "tags": ["博物馆", "科技", "亲子", "互动"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:00-17:15"},
    {"name": "中共一大会址", "category": "cultural", "description": "中国共产党诞生的见证地，典型的上海石库门建筑风格，周边新天地区域时尚与传统交融。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2228, "lng": 121.4705}, "tags": ["红色旅游", "历史", "石库门", "免费"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "思南公馆", "category": "cultural", "description": "上海市中心保存完好的花园洋房建筑群，改造后成为集文化、艺术、餐饮于一体的高端街区。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 31.2152, "lng": 121.4663}, "tags": ["历史建筑", "花园洋房", "拍照", "文化街区"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "田子坊", "category": "cultural", "description": "由石库门里弄改造而成的创意街区，狭窄巷弄里藏着艺术工作室、手作店铺和特色咖啡馆。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2095, "lng": 121.4685}, "tags": ["文创", "石库门", "拍照", "购物"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "新天地", "category": "cultural", "description": "由石库门老建筑改造的高端商业娱乐区域，中西合璧的设计是上海都市更新的经典案例。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.2190, "lng": 121.4730}, "tags": ["石库门", "餐饮", "夜生活", "拍照"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "武康大楼", "category": "cultural", "description": "上海最著名的历史公寓建筑之一，由邬达克设计，独特的船形造型成为武康路乃至上海的城市名片。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.2065, "lng": 121.4365}, "tags": ["历史建筑", "拍照", "网红打卡", "城市名片"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "多伦路文化名人街", "category": "cultural", "description": "一条汇集鲁迅、茅盾、郭沫若等文化名人故居的历史街道，被誉为'中国现代文学的重镇'。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2620, "lng": 121.4810}, "tags": ["历史文化", "名人故居", "建筑", "文学"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "全天"},
    {"name": "朱家角古镇", "category": "cultural", "description": "上海近郊保存最好的江南水乡古镇，小桥流水、明清风貌，被誉为'上海的威尼斯'，适合一日游。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.1008, "lng": 121.0537}, "tags": ["水乡古镇", "江南风情", "拍照", "美食"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "全天"},
    {"name": "七宝古镇", "category": "cultural", "description": "上海近郊的千年古镇，以七宝老街、七宝羊肉和汤圆闻名，距市区较近的江南水乡体验地。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.1576, "lng": 121.3481}, "tags": ["水乡古镇", "美食", "历史文化", "小吃"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "全天"},
    {"name": "召稼楼古镇", "category": "cultural", "description": "上海浦江镇的百年古镇，是沪上农耕文化发源地之一，具有独特的乡村古镇风貌和本地美食。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 31.1100, "lng": 121.5425}, "tags": ["古镇", "乡村风情", "美食", "历史文化"], "suitable_for": ["家庭", "老人"], "opening_hours": "全天"},
    {"name": "上海植物园", "category": "natural", "description": "上海市区的大型植物园，拥有丰富的植物种类和精美的园林景观，春天的樱花和秋天的红叶最为迷人。", "rating": 4.3, "ticket_price_cny": 15, "location": {"lat": 31.1456, "lng": 121.4452}, "tags": ["植物园", "赏花", "自然", "休闲"], "suitable_for": ["家庭", "老人", "儿童", "情侣"], "opening_hours": "07:00-17:00"},
    {"name": "辰山植物园", "category": "natural", "description": "上海规模最大的植物园，由矿坑花园改造而成，温室群和矿坑瀑布是网红打卡点，四季花展丰富。", "rating": 4.5, "ticket_price_cny": 60, "location": {"lat": 31.0747, "lng": 121.1797}, "tags": ["植物园", "赏花", "自然", "拍照", "亲子"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "08:00-17:30"},
    {"name": "上海动物园", "category": "natural", "description": "上海历史悠久的城市动物园，拥有大熊猫、华南虎、金丝猴等珍稀动物，是亲子游和动物爱好者的好去处。", "rating": 4.3, "ticket_price_cny": 40, "location": {"lat": 31.1941, "lng": 121.3613}, "tags": ["动物园", "亲子", "自然", "动物"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "07:30-17:00"},
    {"name": "世纪公园", "category": "natural", "description": "上海内环最大的生态公园，有湖泊、草坪、森林和花园，春日赏花、秋日观叶、四季宜游。", "rating": 4.4, "ticket_price_cny": 10, "location": {"lat": 31.2090, "lng": 121.5509}, "tags": ["城市公园", "赏花", "骑行", "野餐", "休闲"], "suitable_for": ["家庭", "情侣", "老人", "儿童"], "opening_hours": "07:00-18:00"},
    {"name": "共青森林公园", "category": "natural", "description": "上海北部的城市森林公园，以成片的水杉林和草坪闻名，是露营、野餐和森林浴的理想之地。", "rating": 4.3, "ticket_price_cny": 15, "location": {"lat": 31.3230, "lng": 121.5452}, "tags": ["森林公园", "露营", "野餐", "骑行"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "06:00-17:00"},
    {"name": "长风公园", "category": "natural", "description": "上海市中心的综合性公园，以银锄湖和铁臂山为核心景观，可以划船、登山、漫步湖畔。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 31.2249, "lng": 121.3945}, "tags": ["城市公园", "湖泊", "划船", "休闲"], "suitable_for": ["家庭", "老人", "儿童"], "opening_hours": "05:00-21:00"},
    {"name": "上海野生动物园", "category": "natural", "description": "汇集了来自世界各地的珍稀野生动物，可乘车穿越猛兽区近距离观察狮子、老虎等大型动物。", "rating": 4.4, "ticket_price_cny": 130, "location": {"lat": 31.0490, "lng": 121.7265}, "tags": ["动物园", "野生动物", "亲子", "自驾"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "08:00-17:00"},
    {"name": "大宁灵石公园", "category": "natural", "description": "上海北部的大型城市生态公园，以白沙滩和湖景闻名，春天郁金香花展吸引大批市民和游客。", "rating": 4.2, "ticket_price_cny": 2, "location": {"lat": 31.2751, "lng": 121.4506}, "tags": ["城市公园", "沙滩", "赏花", "婚纱摄影"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "05:00-22:00"},
    {"name": "滨江森林公园", "category": "natural", "description": "位于黄浦江与长江交汇处，拥有漫长的滨江岸线和原始湿地景观，是都市人亲近自然的窗口。", "rating": 4.3, "ticket_price_cny": 20, "location": {"lat": 31.3240, "lng": 121.5160}, "tags": ["森林公园", "江景", "湿地", "骑行"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:00-16:30"},
    {"name": "东平国家森林公园", "category": "natural", "description": "崇明岛上最大的森林公园，森林覆盖率高，空气清新，是上海近郊避暑和森林浴的绝佳去处。", "rating": 4.3, "ticket_price_cny": 70, "location": {"lat": 31.6800, "lng": 121.4850}, "tags": ["森林公园", "崇明", "避暑", "骑行", "露营"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:30-16:30"},
    {"name": "佘山国家森林公园", "category": "natural", "description": "上海唯一的自然山林，分为东西两峰，有天文台和天主教堂，是上海少有的登高望远之地。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 31.0900, "lng": 121.1887}, "tags": ["森林公园", "山林", "天文台", "教堂", "登山"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:30-16:30"},
    {"name": "崇明东滩湿地", "category": "natural", "description": "长江口最重要的候鸟迁徙中转站和越冬栖息地，拥有广袤的芦苇荡和丰富的鸟类资源。", "rating": 4.3, "ticket_price_cny": 50, "location": {"lat": 31.5250, "lng": 121.9500}, "tags": ["湿地", "观鸟", "自然保护", "崇明", "生态"], "suitable_for": ["家庭", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "上海迪士尼乐园", "category": "entertainment", "description": "中国大陆首座迪士尼主题乐园，拥有米奇大街、奇幻童话城堡、创极速光轮等经典园区和游乐设施。", "rating": 4.6, "ticket_price_cny": 475, "location": {"lat": 31.1439, "lng": 121.6577}, "tags": ["主题乐园", "亲子", "童话", "刺激", "演出"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "08:30-21:30"},
    {"name": "上海欢乐谷", "category": "entertainment", "description": "上海大型主题乐园，有绝顶雄风、谷木游龙等多个过山车和主题区域，适合追求刺激的游客。", "rating": 4.3, "ticket_price_cny": 260, "location": {"lat": 31.0960, "lng": 121.2133}, "tags": ["主题乐园", "过山车", "刺激", "亲子"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "09:30-18:00"},
    {"name": "上海海洋水族馆", "category": "entertainment", "description": "位于陆家嘴的世界级水族馆，拥有世界上最长的海底隧道之一，可观赏来自五大洲的海洋生物。", "rating": 4.5, "ticket_price_cny": 160, "location": {"lat": 31.2363, "lng": 121.5007}, "tags": ["水族馆", "海洋动物", "亲子", "陆家嘴"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "09:00-18:00"},
    {"name": "上海长风海洋世界", "category": "entertainment", "description": "位于长风公园内的室内海洋馆，有白鲸表演和触摸池互动体验，是亲子海洋科普的好去处。", "rating": 4.2, "ticket_price_cny": 180, "location": {"lat": 31.2250, "lng": 121.3950}, "tags": ["海洋馆", "亲子", "白鲸", "互动"], "suitable_for": ["家庭", "儿童"], "opening_hours": "08:30-17:00"},
    {"name": "上海大世界", "category": "entertainment", "description": "百年历史的娱乐场所，以哈哈镜和非遗表演著称，'不到大世界，枉来大上海'曾是一代上海人的口头禅。", "rating": 4.2, "ticket_price_cny": 60, "location": {"lat": 31.2331, "lng": 121.4742}, "tags": ["历史建筑", "非遗", "特色演出", "文化娱乐"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "上海马戏城", "category": "entertainment", "description": "上海标志性的杂技表演场馆，ERA时空之旅将传统杂技与现代科技融合，是上海最受欢迎的驻场演出之一。", "rating": 4.5, "ticket_price_cny": 280, "location": {"lat": 31.2632, "lng": 121.4531}, "tags": ["杂技", "演出", "马戏", "ERA"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "演出时间详见排期"},
    {"name": "上海当代艺术博物馆", "category": "entertainment", "description": "中国首家公立当代艺术博物馆，由原南市发电厂改造而成，举办上海双年展等重要当代艺术展览。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 31.2025, "lng": 121.4980}, "tags": ["博物馆", "当代艺术", "展览", "工业改造", "免费"], "suitable_for": ["情侣", "独行"], "opening_hours": "11:00-19:00"},
    {"name": "上海自然博物馆", "category": "entertainment", "description": "上海最受欢迎的博物馆之一，以恐龙骨架、非洲草原全景等场景化展陈为特色，是自然科学的宝库。", "rating": 4.6, "ticket_price_cny": 30, "location": {"lat": 31.2368, "lng": 121.4559}, "tags": ["博物馆", "自然科学", "亲子", "恐龙"], "suitable_for": ["家庭", "儿童", "独行"], "opening_hours": "09:00-17:15"},
    {"name": "金茂大厦88层观光厅", "category": "entertainment", "description": "位于金茂大厦88层的观光平台，可360度俯瞰浦江两岸美景，高速电梯从底层到88层仅需45秒。", "rating": 4.4, "ticket_price_cny": 120, "location": {"lat": 31.2360, "lng": 121.5030}, "tags": ["观光厅", "高空", "夜景", "陆家嘴", "拍照"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:30-21:30"},
    {"name": "东方明珠广播电视塔", "category": "entertainment", "description": "上海最具辨识度的地标建筑，设有观光层和悬空玻璃观景廊，浦江两岸壮丽景色尽收眼底。", "rating": 4.4, "ticket_price_cny": 199, "location": {"lat": 31.2397, "lng": 121.4998}, "tags": ["城市地标", "观光塔", "玻璃栈道", "陆家嘴", "拍照"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:00-21:30"},
    {"name": "南京路步行街", "category": "shopping", "description": "中国最著名的商业街之一，东起外滩西至人民广场，百年老字号与国际品牌云集，是上海购物的必到之地。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.2360, "lng": 121.4725}, "tags": ["购物", "商业街", "美食", "城市地标"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "全天"},
    {"name": "淮海路", "category": "shopping", "description": "上海最具格调的商业街之一，汇聚国际奢侈品牌与潮流店铺，沿街法租界梧桐树影营造优雅氛围。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.2170, "lng": 121.4646}, "tags": ["购物", "时尚", "奢侈品", "法租界"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "陆家嘴正大广场", "category": "shopping", "description": "上海陆家嘴核心区域的大型购物中心，紧邻东方明珠，汇集零售、餐饮、娱乐，是浦东商业地标。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2372, "lng": 121.5045}, "tags": ["购物中心", "陆家嘴", "餐饮", "零售"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "徐家汇商圈", "category": "shopping", "description": "上海西南最大的商业中心，港汇恒隆广场、美罗城、东方商厦等云集，是上海老牌商圈之一。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 31.1940, "lng": 121.4374}, "tags": ["商圈", "购物", "餐饮", "百货"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "静安寺商圈", "category": "shopping", "description": "以静安寺为核心的繁华商圈，久光百货、芮欧百货和静安嘉里中心环绕，是高端购物与商务聚集地。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 31.2237, "lng": 121.4480}, "tags": ["商圈", "高端购物", "餐饮", "商务"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "上海环球港", "category": "shopping", "description": "上海中心城区规模最大的购物中心之一，欧式建筑风格，汇集数百个品牌和餐饮，屋顶花园独具特色。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2325, "lng": 121.4125}, "tags": ["购物中心", "欧式建筑", "餐饮", "亲子"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "上海大悦城", "category": "shopping", "description": "苏州河畔的时尚购物中心，屋顶摩天轮是特色地标，集购物、餐饮、娱乐和网红打卡于一体。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.2430, "lng": 121.4650}, "tags": ["购物中心", "摩天轮", "网红打卡", "餐饮"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "来福士广场", "category": "shopping", "description": "位于人民广场核心位置的时尚购物商场，品牌丰富，地理位置优越，是上海年轻人聚会的热门场所。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 31.2320, "lng": 121.4745}, "tags": ["购物中心", "时尚", "餐饮", "人民广场"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "日月光中心", "category": "shopping", "description": "打浦桥地铁上盖大型商住综合体，美食广场和各类餐饮店铺林立，是吃货和年轻人的聚集地。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 31.2080, "lng": 121.4665}, "tags": ["购物中心", "美食", "餐饮", "田子坊"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "IFC国金中心", "category": "shopping", "description": "陆家嘴金融核心区的高端购物中心，云集全球顶级奢侈品牌，建筑设计现代大气，是上海奢侈品购物的标杆。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 31.2365, "lng": 121.5040}, "tags": ["购物中心", "奢侈品", "高端", "陆家嘴"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
]


def seed():
    print(f"Seeding {len(SHANGHAI_ATTRACTIONS)} Shanghai attractions...")
    store = get_chroma_store()

    existing = store.search_attractions("上海", city="上海", k=1)
    if existing:
        print(f"Shanghai data already exists ({store.collection_count('attractions')} total). Delete first if re-seed.")
        return

    # Add city field to each attraction
    for a in SHANGHAI_ATTRACTIONS:
        a["city"] = "上海"

    n = store.add_attractions(SHANGHAI_ATTRACTIONS)
    print(f"Done! Added {n} attractions to ChromaDB.")

    # Verify
    print(f"Collection count: {store.collection_count('attractions')}")

    # Quick semantic search test
    results = store.search_attractions("适合老人的自然景点", city="上海", k=3)
    print(f"\nSemantic search test '适合老人的自然景点':")
    for r in results:
        print(f"  - {r['name']} (score: {r['_chroma_score']:.3f})")


if __name__ == "__main__":
    seed()
