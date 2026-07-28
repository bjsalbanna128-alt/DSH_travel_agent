"""Seed Chengdu attractions into ChromaDB for semantic search."""

import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_chengdu
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

CHENGDU_ATTRACTIONS = [
    {"name": "宽窄巷子", "category": "cultural", "description": "成都遗留下来的较成规模的清朝古街道，由宽巷子、窄巷子、井巷子平行排列组成，全为青黛砖瓦的仿古四合院落。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 30.6745, "lng": 104.0528}, "tags": ["历史文化", "拍照", "美食"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "全天"},
    {"name": "锦里古街", "category": "cultural", "description": "成都最古老的商业街之一，以三国文化为主题，有各种传统工艺品、小吃和茶馆，夜晚灯火辉煌。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 30.6435, "lng": 104.0458}, "tags": ["历史文化", "美食", "购物"], "suitable_for": ["家庭", "情侣"], "opening_hours": "09:00-22:00"},
    {"name": "武侯祠", "category": "cultural", "description": "纪念三国时期蜀汉丞相诸葛亮的祠堂，中国唯一一座君臣合祀祠庙，三国文化爱好者的圣地。", "rating": 4.6, "ticket_price_cny": 60, "location": {"lat": 30.6456, "lng": 104.0467}, "tags": ["历史文化", "三国"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-18:00"},
    {"name": "杜甫草堂", "category": "cultural", "description": "唐代大诗人杜甫流寓成都时的故居，园内竹林掩映、古朴幽静，是中国文学史上的圣地。", "rating": 4.5, "ticket_price_cny": 60, "location": {"lat": 30.6586, "lng": 104.0267}, "tags": ["历史文化", "文学", "园林"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-18:30"},
    {"name": "大熊猫繁育研究基地", "category": "natural", "description": "世界著名的大熊猫迁地保护基地，可近距离观赏大熊猫、小熊猫等珍稀动物，尤其是憨态可掬的熊猫幼崽。", "rating": 4.7, "ticket_price_cny": 55, "location": {"lat": 30.7335, "lng": 104.1472}, "tags": ["自然", "亲子", "拍照"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "07:30-18:00"},
    {"name": "都江堰", "category": "natural", "description": "世界文化遗产，两千多年前李冰父子修建的水利工程，至今仍在发挥作用，体现古人智慧。", "rating": 4.6, "ticket_price_cny": 90, "location": {"lat": 30.9875, "lng": 103.6158}, "tags": ["自然风光", "历史文化", "工程奇迹"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-17:30"},
    {"name": "青城山", "category": "natural", "description": "道教名山，分为前山和后山，前山道教文化浓郁，后山自然风光秀丽，是徒步和养生胜地。", "rating": 4.5, "ticket_price_cny": 90, "location": {"lat": 30.9000, "lng": 103.5667}, "tags": ["自然风光", "道教文化", "徒步"], "suitable_for": ["独行", "情侣"], "opening_hours": "08:00-17:00"},
    {"name": "春熙路", "category": "shopping", "description": "成都最繁华的商业街，汇集各大品牌、百货商场和美食，IFS楼顶的爬墙熊猫是打卡地标。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.6580, "lng": 104.0802}, "tags": ["购物", "美食", "拍照"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "太古里", "category": "shopping", "description": "毗邻春熙路的高端开放式购物街区，现代设计与传统建筑融合，网红店铺和旗舰店云集。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 30.6545, "lng": 104.0843}, "tags": ["购物", "拍照", "建筑"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "文殊院", "category": "cultural", "description": "成都市区内保存最完整的佛教寺院之一，始建于隋朝，院内香火鼎盛，周边有素斋和茶馆。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.6752, "lng": 104.0703}, "tags": ["宗教文化", "历史", "素食"], "suitable_for": ["家庭", "老人"], "opening_hours": "07:00-17:30"},
    {"name": "金沙遗址博物馆", "category": "cultural", "description": "展示距今3000多年的古蜀文明遗址，太阳神鸟金饰是镇馆之宝，也是中国文化遗产标志。", "rating": 4.5, "ticket_price_cny": 80, "location": {"lat": 30.6815, "lng": 104.0123}, "tags": ["博物馆", "历史文化", "考古"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-18:00"},
    {"name": "人民公园", "category": "natural", "description": "成都最接地气的公园，鹤鸣茶社喝盖碗茶、掏耳朵、看大爷大妈打麻将，体验真正的成都慢生活。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6594, "lng": 104.0603}, "tags": ["公园", "茶文化", "慢生活"], "suitable_for": ["家庭", "老人"], "opening_hours": "06:00-22:00"},
    {"name": "九眼桥", "category": "entertainment", "description": "成都夜生活地标，锦江上的古桥，两岸酒吧街热闹非凡，适合夜晚散步和体验成都夜文化。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6440, "lng": 104.0885}, "tags": ["夜生活", "酒吧", "江景"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "天府广场", "category": "cultural", "description": "成都市中心地标，周边有四川科技馆、四川省图书馆、成都博物馆等文化场馆。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.6577, "lng": 104.0658}, "tags": ["城市地标", "博物馆"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "全天"},
    {"name": "黄龙溪古镇", "category": "cultural", "description": "成都近郊保存完好的川西古镇，青石板路、木质吊脚楼、溪水穿镇而过，适合一日游。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.3111, "lng": 103.9794}, "tags": ["古镇", "历史文化", "拍照"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "全天"},
    {"name": "洛带古镇", "category": "cultural", "description": "成都近郊的客家古镇，有保存完好的客家会馆群和土楼建筑，可以品尝正宗客家菜。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.6389, "lng": 104.3242}, "tags": ["古镇", "客家文化", "美食"], "suitable_for": ["家庭", "老人"], "opening_hours": "全天"},
    {"name": "东郊记忆", "category": "entertainment", "description": "前身为成都国营红光电子管厂，改造后成为文创园区，有音乐演出、艺术展览和创意店铺。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.6642, "lng": 104.1246}, "tags": ["文创", "音乐", "拍照", "工业风"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "望江楼公园", "category": "natural", "description": "纪念唐代女诗人薛涛的公园，以竹子品种最多而闻名全国，锦江畔的竹林幽径别有韵味。", "rating": 4.2, "ticket_price_cny": 20, "location": {"lat": 30.6333, "lng": 104.0906}, "tags": ["公园", "文学", "竹文化"], "suitable_for": ["家庭", "老人"], "opening_hours": "08:00-18:00"},
    {"name": "成都欢乐谷", "category": "entertainment", "description": "大型主题乐园，有过山车、水上乐园、演出等多种娱乐项目，适合家庭和年轻人游玩。", "rating": 4.3, "ticket_price_cny": 230, "location": {"lat": 30.7270, "lng": 104.0405}, "tags": ["主题乐园", "亲子", "刺激"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:30-18:00"},
    {"name": "成都海昌极地海洋公园", "category": "entertainment", "description": "西南地区最大的海洋主题公园，有企鹅、白鲸、海豚等极地和海洋动物表演和展示。", "rating": 4.4, "ticket_price_cny": 200, "location": {"lat": 30.5586, "lng": 104.0689}, "tags": ["海洋动物", "亲子", "表演"], "suitable_for": ["家庭", "儿童"], "opening_hours": "09:00-17:30"},
    {"name": "成都博物馆", "category": "cultural", "description": "位于天府广场西侧，展示成都从远古到近代的历史变迁，馆藏丰富且免费参观。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 30.6585, "lng": 104.0632}, "tags": ["博物馆", "历史文化", "免费"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "四川博物院", "category": "cultural", "description": "西南地区最大的综合性博物馆，收藏了大量巴蜀青铜器、张大千书画和汉代画像砖。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.6610, "lng": 104.0317}, "tags": ["博物馆", "历史文化", "艺术"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "浣花溪公园", "category": "natural", "description": "成都市区最大的开放式森林公园，以杜甫草堂为文化背景，湖水、白鹭、竹林构成诗意画卷。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6567, "lng": 104.0292}, "tags": ["公园", "自然", "休闲"], "suitable_for": ["家庭", "老人"], "opening_hours": "06:00-22:00"},
    {"name": "西岭雪山", "category": "natural", "description": "距成都约95公里的高山滑雪场和避暑胜地，冬季可滑雪，夏季可登山赏花，\"窗含西岭千秋雪\"指的就是这里。", "rating": 4.4, "ticket_price_cny": 200, "location": {"lat": 30.7042, "lng": 103.2658}, "tags": ["雪山", "滑雪", "徒步", "自然"], "suitable_for": ["情侣", "独行"], "opening_hours": "08:00-17:00"},
    {"name": "青羊宫", "category": "cultural", "description": "成都最古老的道教宫观之一，始建于周朝，被誉为\'川西第一道观\'，内有著名的八卦亭和铜羊。", "rating": 4.2, "ticket_price_cny": 10, "location": {"lat": 30.6675, "lng": 104.0520}, "tags": ["道教文化", "历史", "古建筑"], "suitable_for": ["家庭", "老人"], "opening_hours": "08:00-18:00"},
    {"name": "大慈寺", "category": "cultural", "description": "位于太古里旁边的千年古刹，始建于魏晋时期，是闹市中的一方净土，玄奘法师曾在此受戒。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6528, "lng": 104.0850}, "tags": ["佛教文化", "历史", "古建筑"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "07:00-17:00"},
    {"name": "安顺廊桥", "category": "cultural", "description": "横跨锦江的古桥，夜景极美，是成都的标志性建筑之一，附近有酒吧和餐厅。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6456, "lng": 104.0894}, "tags": ["古桥", "夜景", "拍照"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "三圣花乡", "category": "natural", "description": "成都东郊的乡村旅游示范区，有花海、农家乐、创意工坊，是成都人周末休闲的热门去处。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 30.5875, "lng": 104.1608}, "tags": ["花海", "农家乐", "亲子"], "suitable_for": ["家庭", "儿童", "老人"], "opening_hours": "全天"},
    {"name": "成都动物园", "category": "natural", "description": "成都市区内的大型动物园，有300多种动物，包括大熊猫、金丝猴等珍稀物种，适合亲子游。", "rating": 4.2, "ticket_price_cny": 20, "location": {"lat": 30.7040, "lng": 104.1060}, "tags": ["动物园", "亲子", "自然"], "suitable_for": ["家庭", "儿童"], "opening_hours": "08:00-17:00"},
    {"name": "蜀锦织绣博物馆", "category": "cultural", "description": "展示国家级非物质文化遗产蜀锦和蜀绣的专题博物馆，可观看传统织机现场操作。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.6470, "lng": 104.0550}, "tags": ["博物馆", "非遗", "手工艺"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "成都规划馆", "category": "cultural", "description": "展示成都城市规划和未来发展的展馆，有大型城市沙盘模型和互动体验项目。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 30.5820, "lng": 104.0650}, "tags": ["博物馆", "城市规划", "亲子"], "suitable_for": ["家庭", "儿童"], "opening_hours": "09:00-17:00"},
    {"name": "活水公园", "category": "natural", "description": "世界上第一座以水为主题的城市生态环境公园，展示人工湿地污水处理系统，寓教于乐。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 30.6680, "lng": 104.0920}, "tags": ["公园", "生态", "亲子"], "suitable_for": ["家庭", "儿童", "老人"], "opening_hours": "06:00-22:00"},
    {"name": "塔子山公园", "category": "natural", "description": "成都东部的综合性公园，有鸟语林、九天楼等景点，春季赏花和秋季登高是特色活动。", "rating": 4.0, "ticket_price_cny": 0, "location": {"lat": 30.6320, "lng": 104.1280}, "tags": ["公园", "赏花", "休闲"], "suitable_for": ["家庭", "老人"], "opening_hours": "06:00-22:00"},
    {"name": "成都植物园", "category": "natural", "description": "拥有丰富的植物种类和优美的园林景观，春天樱花季和秋天红叶季是最佳游览时间。", "rating": 4.2, "ticket_price_cny": 10, "location": {"lat": 30.7560, "lng": 104.1410}, "tags": ["植物园", "赏花", "自然"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "08:00-17:30"},
    {"name": "成都露天音乐公园", "category": "entertainment", "description": "国内最大的露天音乐主题公园，有大型演出场地和户外休闲空间，经常举办音乐节和文艺活动。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.7500, "lng": 104.0830}, "tags": ["音乐", "演出", "休闲"], "suitable_for": ["情侣", "独行"], "opening_hours": "09:00-21:00"},
    {"name": "铁像寺水街", "category": "shopping", "description": "成都南门的一个文创街区，小桥流水、茶馆和特色店铺，比宽窄巷子更安静更有生活气息。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.5600, "lng": 104.0560}, "tags": ["文创", "茶馆", "拍照"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "桂溪生态公园", "category": "natural", "description": "成都南门的大型城市生态公园，有湖泊、草坪和骑行道，是城市中的绿肺。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.5670, "lng": 104.0730}, "tags": ["公园", "骑行", "跑步", "野餐"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "全天"},
    {"name": "兴隆湖", "category": "natural", "description": "成都科学城核心区的人工湖，湖水清澈，环湖有超过8公里的绿道，适合骑行和跑步。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.4000, "lng": 104.0800}, "tags": ["湖泊", "骑行", "跑步", "自然"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "明月村", "category": "cultural", "description": "成都蒲江县的文创乡村，有陶艺、扎染等手工体验，是文艺青年喜爱的世外桃源。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.3000, "lng": 103.4200}, "tags": ["文创", "手工艺", "乡村"], "suitable_for": ["情侣", "家庭"], "opening_hours": "全天"},
    {"name": "安仁古镇", "category": "cultural", "description": "成都大邑县的民国风情古镇，有刘氏庄园和建川博物馆聚落，是了解川西近代历史的好去处。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 30.5800, "lng": 103.6200}, "tags": ["古镇", "民国风情", "博物馆"], "suitable_for": ["家庭", "老人"], "opening_hours": "全天"},
    {"name": "四川大学望江校区", "category": "cultural", "description": "百年名校的老校区，校园内绿树成荫、荷花池畔适合散步，秋天银杏大道是网红打卡点。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 30.6350, "lng": 104.0850}, "tags": ["校园", "银杏", "拍照"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "琴台路", "category": "cultural", "description": "以司马相如和卓文君爱情故事为主题的文化街区，仿汉建筑、珠宝店和高级餐厅云集。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 30.6610, "lng": 104.0520}, "tags": ["历史文化", "购物", "美食"], "suitable_for": ["情侣", "家庭"], "opening_hours": "全天"},
    {"name": "成都当代影像馆", "category": "cultural", "description": "国内首家专注于摄影和当代影像艺术的非营利美术馆，展出中外摄影大师作品。", "rating": 4.3, "ticket_price_cny": 60, "location": {"lat": 30.7100, "lng": 104.0420}, "tags": ["美术馆", "摄影", "艺术"], "suitable_for": ["独行", "情侣"], "opening_hours": "10:00-18:00"},
    {"name": "江滩公园", "category": "natural", "description": "成都锦江边的滨水公园，有五岔子大桥等地标建筑，夜景漂亮，适合散步和骑行。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 30.5620, "lng": 104.0720}, "tags": ["公园", "江景", "夜景"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "全天"},
    {"name": "空港花田", "category": "natural", "description": "成都双流机场旁的花海公园，可以近距离看飞机起降，花季时大片花海+飞机同框的独特拍照地。", "rating": 4.2, "ticket_price_cny": 30, "location": {"lat": 30.5500, "lng": 103.9600}, "tags": ["花海", "拍照", "飞机"], "suitable_for": ["情侣", "家庭", "儿童"], "opening_hours": "09:00-18:00"},
    {"name": "紫颐香薰山谷", "category": "natural", "description": "成都双流的薰衣草庄园，夏季有大片薰衣草和马鞭草花海，是浪漫拍照圣地。", "rating": 4.0, "ticket_price_cny": 60, "location": {"lat": 30.4700, "lng": 104.0200}, "tags": ["花海", "拍照", "浪漫"], "suitable_for": ["情侣", "家庭"], "opening_hours": "09:00-17:30"},
    {"name": "浩海立方海洋馆", "category": "entertainment", "description": "位于成都双流的大型室内海洋馆，有世界最大的水族观景窗之一，鲨鱼、鳐鱼等海洋生物丰富。", "rating": 4.3, "ticket_price_cny": 160, "location": {"lat": 30.5850, "lng": 103.9200}, "tags": ["海洋馆", "亲子", "室内"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "10:00-20:00"},
    {"name": "国色天乡乐园", "category": "entertainment", "description": "成都温江的大型主题乐园群，包含陆地乐园和水上乐园，有过山车、摩天轮等游乐设施。", "rating": 4.2, "ticket_price_cny": 150, "location": {"lat": 30.7300, "lng": 103.8200}, "tags": ["主题乐园", "亲子", "水上乐园"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:30-18:00"},
    {"name": "街子古镇", "category": "cultural", "description": "成都崇州的川西古镇，毗邻青城山，古镇与山水相依，味江河穿镇而过，被誉为\'青城后花园\'。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 30.8300, "lng": 103.5800}, "tags": ["古镇", "自然", "休闲"], "suitable_for": ["家庭", "老人"], "opening_hours": "全天"},
    {"name": "白鹿镇", "category": "cultural", "description": "成都彭州的法式风情小镇，有百年历史的圣母领报堂（上书院），中法文化交融的独特古镇。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 31.0800, "lng": 103.9200}, "tags": ["法式风情", "教堂", "拍照"], "suitable_for": ["情侣", "家庭"], "opening_hours": "全天"},
]


def seed():
    print(f"Seeding {len(CHENGDU_ATTRACTIONS)} Chengdu attractions...")
    store = get_chroma_store()

    # Check if this city's data already exists
    existing = store.search_attractions("成都", city="成都", k=1)
    if existing:
        print(f"Chengdu data already exists ({store.collection_count('attractions')} total). Delete first if re-seed.")
        return

    # Add city field to each attraction
    for a in CHENGDU_ATTRACTIONS:
        a["city"] = "成都"

    n = store.add_attractions(CHENGDU_ATTRACTIONS)
    print(f"Done! Added {n} attractions to ChromaDB.")

    # Verify
    print(f"Collection count: {store.collection_count('attractions')}")

    # Quick semantic search test
    results = store.search_attractions("适合老人的自然景点", city="成都", k=3)
    print(f"\nSemantic search test '适合老人的自然景点':")
    for r in results:
        print(f"  - {r['name']} (score: {r['_chroma_score']:.3f})")


if __name__ == "__main__":
    seed()
