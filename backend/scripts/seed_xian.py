"""Seed Xi'an attractions into ChromaDB for semantic search."""

import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_xian
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

XIAN_ATTRACTIONS = [
    {"name": "兵马俑", "category": "cultural", "description": "世界第八大奇迹，秦始皇陵的陪葬坑，数千个真人大小陶俑与真人一样大小、神态各异，展现了两千多年前秦军的威武之师。", "rating": 4.8, "ticket_price_cny": 120, "location": {"lat": 34.3856, "lng": 109.2733}, "tags": ["世界遗产", "历史文化", "考古"], "suitable_for": ["家庭", "独行", "老人"], "opening_hours": "08:30-17:00"},
    {"name": "秦始皇陵", "category": "cultural", "description": "中国历史上第一位皇帝秦始皇的陵墓，规模宏大，据传内部有用水银做的江河大海，至今未完全发掘。", "rating": 4.6, "ticket_price_cny": 120, "location": {"lat": 34.3810, "lng": 109.2550}, "tags": ["世界遗产", "历史文化", "帝王陵墓"], "suitable_for": ["家庭", "独行", "老人"], "opening_hours": "08:30-17:00"},
    {"name": "大雁塔", "category": "cultural", "description": "西安的地标建筑，唐代玄奘法师为保存从天竺带回的经卷佛像而主持修建，七层砖塔巍峨壮观，周边有大慈恩寺。", "rating": 4.6, "ticket_price_cny": 40, "location": {"lat": 34.2198, "lng": 108.9590}, "tags": ["佛教文化", "古建筑", "地标"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-17:30"},
    {"name": "小雁塔", "category": "cultural", "description": "唐代密檐式砖塔的典范，历经千年风雨和多次地震仍巍然屹立，塔下的西安博物院馆藏丰富且免费参观。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 34.2412, "lng": 108.9375}, "tags": ["古建筑", "博物馆", "佛教文化"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "西安城墙", "category": "cultural", "description": "中国现存规模最大、保存最完整的古代城垣，全长13.7公里，可在城墙上骑行或漫步，俯瞰古城风貌。", "rating": 4.7, "ticket_price_cny": 54, "location": {"lat": 34.2602, "lng": 108.9425}, "tags": ["古建筑", "骑行", "地标", "历史文化"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:00-22:00"},
    {"name": "钟楼", "category": "cultural", "description": "位于西安城中心的明代建筑，是中国现存钟楼中形制最大、保存最完整的一座，登楼可俯瞰四条大街。", "rating": 4.5, "ticket_price_cny": 30, "location": {"lat": 34.2610, "lng": 108.9422}, "tags": ["古建筑", "地标", "历史文化"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-18:00"},
    {"name": "鼓楼", "category": "cultural", "description": "与钟楼遥相呼应的明代建筑，楼上有二十四节气鼓陈列，登楼可远眺回民街和钟楼，视野极佳。", "rating": 4.5, "ticket_price_cny": 30, "location": {"lat": 34.2620, "lng": 108.9420}, "tags": ["古建筑", "历史文化", "地标"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-18:00"},
    {"name": "回民街", "category": "cultural", "description": "西安最著名的小吃街，汇集了羊肉泡馍、肉夹馍、凉皮等众多西北特色美食，夜晚热闹非凡，是吃货的天堂。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 34.2634, "lng": 108.9410}, "tags": ["美食", "历史文化", "逛街"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "全天"},
    {"name": "陕西历史博物馆", "category": "cultural", "description": "中国第一座大型现代化国家级博物馆，馆藏文物170余万件，从商周青铜器到唐代金银器，被誉为'古都明珠，华夏宝库'。", "rating": 4.7, "ticket_price_cny": 0, "location": {"lat": 34.2206, "lng": 108.9524}, "tags": ["博物馆", "历史文化", "国宝"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:30"},
    {"name": "华清宫", "category": "cultural", "description": "唐代皇家温泉离宫，杨贵妃曾在此沐浴，也是西安事变的发生地。骊山脚下，温泉水滑，历史典故众多。", "rating": 4.5, "ticket_price_cny": 120, "location": {"lat": 34.3589, "lng": 109.2069}, "tags": ["皇家园林", "历史文化", "温泉"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "07:30-18:00"},
    {"name": "大唐芙蓉园", "category": "cultural", "description": "仿唐代皇家园林风格建造的大型文化主题公园，园内亭台楼阁、水幕电影和唐代歌舞表演精彩纷呈。", "rating": 4.4, "ticket_price_cny": 120, "location": {"lat": 34.2145, "lng": 108.9700}, "tags": ["皇家园林", "仿古建筑", "演出"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "09:00-22:00"},
    {"name": "大明宫国家遗址公园", "category": "cultural", "description": "唐代最宏伟的宫殿建筑群遗址，曾是世界上规模最大的宫殿，如今作为遗址公园开放，可了解唐代宫廷文化。", "rating": 4.3, "ticket_price_cny": 60, "location": {"lat": 34.2950, "lng": 108.9618}, "tags": ["遗址公园", "历史文化", "唐代"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:30-18:00"},
    {"name": "碑林博物馆", "category": "cultural", "description": "中国最大的石刻艺术博物馆，收藏了从汉代到清代的碑石墓志三千余件，是书法爱好者的朝圣之地。", "rating": 4.5, "ticket_price_cny": 65, "location": {"lat": 34.2548, "lng": 108.9476}, "tags": ["博物馆", "书法", "石刻艺术"], "suitable_for": ["独行", "老人", "家庭"], "opening_hours": "08:00-18:00"},
    {"name": "半坡博物馆", "category": "cultural", "description": "中国第一座史前遗址博物馆，展示了距今6000多年的仰韶文化村落遗址，可直观了解原始社会的生活面貌。", "rating": 4.2, "ticket_price_cny": 55, "location": {"lat": 34.2747, "lng": 109.0519}, "tags": ["博物馆", "史前文化", "考古"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-17:30"},
    {"name": "青龙寺", "category": "cultural", "description": "唐代佛教密宗祖庭，日本真言宗祖庭，每年春天樱花盛开时是西安最美的赏樱胜地，文化底蕴深厚。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2340, "lng": 109.0030}, "tags": ["佛教文化", "赏樱", "古建筑"], "suitable_for": ["情侣", "家庭", "老人"], "opening_hours": "08:00-17:00"},
    {"name": "兴庆宫公园", "category": "cultural", "description": "唐代兴庆宫遗址上修建的公园，曾是唐玄宗与杨贵妃居住地，园内有沉香亭等古迹，春天牡丹盛开十分美丽。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.2499, "lng": 108.9893}, "tags": ["公园", "历史文化", "赏花"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "06:00-22:00"},
    {"name": "书院门", "category": "cultural", "description": "西安著名的文化街区，因关中书院而得名，青石板路上遍布笔墨纸砚、书画古玩店铺，充满文人气息。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2552, "lng": 108.9450}, "tags": ["文化街区", "书画", "逛街"], "suitable_for": ["独行", "老人", "情侣"], "opening_hours": "全天"},
    {"name": "八路军西安办事处纪念馆", "category": "cultural", "description": "抗日战争时期八路军在西安的公开办事机构旧址，红色旅游经典景区，展示了那段波澜壮阔的革命历史。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 34.2685, "lng": 108.9568}, "tags": ["红色旅游", "纪念馆", "抗日战争"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "汉阳陵", "category": "cultural", "description": "汉景帝刘启及其皇后的合葬陵园，地下博物馆采用先进的玻璃通道设计，可近距离观看汉代陪葬坑。", "rating": 4.3, "ticket_price_cny": 70, "location": {"lat": 34.4422, "lng": 108.9360}, "tags": ["帝王陵墓", "博物馆", "汉代文化"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:30-17:00"},
    {"name": "楼观台", "category": "cultural", "description": "道教祖庭，老子在此讲授《道德经》，有说经台、宗圣宫等古迹，终南山下的道教文化圣地。", "rating": 4.2, "ticket_price_cny": 55, "location": {"lat": 34.0576, "lng": 108.3300}, "tags": ["道教文化", "古建筑", "自然风光"], "suitable_for": ["独行", "老人", "家庭"], "opening_hours": "08:30-17:30"},
    {"name": "骊山", "category": "natural", "description": "秦岭北麓的风景名山，山势秀丽、松柏满山，有烽火台、老母宫等景点，周秦汉唐均在此留下历史印记。", "rating": 4.4, "ticket_price_cny": 60, "location": {"lat": 34.3530, "lng": 109.2100}, "tags": ["自然风光", "历史文化", "登山"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "08:00-18:00"},
    {"name": "翠华山", "category": "natural", "description": "终南山的著名山峰，以山崩地貌和天池闻名，是秦岭终南山世界地质公园的核心景区，四季景色各异。", "rating": 4.3, "ticket_price_cny": 65, "location": {"lat": 33.9833, "lng": 109.0167}, "tags": ["自然风光", "地质奇观", "登山"], "suitable_for": ["独行", "情侣", "家庭"], "opening_hours": "08:00-17:00"},
    {"name": "终南山", "category": "natural", "description": "秦岭山脉的主峰之一，自古以来就是隐士修道之地，也是'寿比南山'典故的出处，风景秀丽、仙气缭绕。", "rating": 4.4, "ticket_price_cny": 50, "location": {"lat": 33.9333, "lng": 108.9833}, "tags": ["自然风光", "道教文化", "登山"], "suitable_for": ["独行", "情侣"], "opening_hours": "全天"},
    {"name": "太平国家森林公园", "category": "natural", "description": "以瀑布群和紫荆花海闻名的国家森林公园，拥有落差近百米的彩虹瀑布，夏季避暑、春赏花海的绝佳去处。", "rating": 4.3, "ticket_price_cny": 60, "location": {"lat": 33.9333, "lng": 108.6667}, "tags": ["自然风光", "瀑布", "避暑"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "08:00-17:00"},
    {"name": "朱雀国家森林公园", "category": "natural", "description": "秦岭深处的原始森林景区，有高山草甸、冰晶顶等景观，空气清新，是户外徒步爱好者的天堂。", "rating": 4.2, "ticket_price_cny": 50, "location": {"lat": 33.8500, "lng": 108.5667}, "tags": ["自然风光", "徒步", "森林"], "suitable_for": ["独行", "情侣"], "opening_hours": "08:00-17:00"},
    {"name": "秦岭野生动物园", "category": "natural", "description": "西北地区最大的野生动物园，有大熊猫、金丝猴、朱鹮等秦岭四宝以及猛兽区、草原区等多种动物展示。", "rating": 4.2, "ticket_price_cny": 100, "location": {"lat": 34.0556, "lng": 108.8417}, "tags": ["动物园", "亲子", "自然"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:00-17:30"},
    {"name": "西安植物园", "category": "natural", "description": "新园区位于曲江新区，收集植物4000余种，四季花海不断，春天的郁金香展和秋天的菊花展最为出名。", "rating": 4.1, "ticket_price_cny": 10, "location": {"lat": 34.2083, "lng": 109.0167}, "tags": ["植物园", "赏花", "亲子"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "08:00-18:00"},
    {"name": "环城公园", "category": "natural", "description": "环绕西安城墙一周的带状公园，护城河绿树成荫，是市民晨练、散步和休闲的好去处，可近距离感受古城墙的雄伟。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.2590, "lng": 108.9400}, "tags": ["公园", "城墙", "休闲"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "全天"},
    {"name": "曲江池遗址公园", "category": "natural", "description": "唐代曲江池皇家园林遗址上复建的公园，湖光潋滟、杨柳依依，是市民和游客休闲散步的热门去处。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2056, "lng": 108.9750}, "tags": ["公园", "湖泊", "历史文化"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "全天"},
    {"name": "浐灞国家湿地公园", "category": "natural", "description": "西安东北部的城市湿地公园，生态环境优美，是观鸟和亲近自然的理想场所，周末家庭出游的好选择。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 34.3425, "lng": 109.0250}, "tags": ["湿地", "观鸟", "亲子"], "suitable_for": ["家庭", "儿童", "老人"], "opening_hours": "09:00-17:00"},
    {"name": "大唐不夜城步行街", "category": "entertainment", "description": "西安最火爆的夜间文旅街区，以唐风建筑和灯光秀著称，有各种行为艺术表演和网红打卡点，再现盛唐繁华景象。", "rating": 4.6, "ticket_price_cny": 0, "location": {"lat": 34.2138, "lng": 108.9650}, "tags": ["夜景", "演出", "拍照", "美食"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "全天"},
    {"name": "白鹿原影视城", "category": "entertainment", "description": "以陈忠实小说《白鹿原》为主题的影视拍摄基地，复原了关中传统村落和民国街景，有丰富的实景演出。", "rating": 4.2, "ticket_price_cny": 80, "location": {"lat": 34.1883, "lng": 109.1583}, "tags": ["影视基地", "文化体验", "实景演出"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "09:00-18:00"},
    {"name": "西安世博园", "category": "entertainment", "description": "2011年西安世界园艺博览会会址，园内有长安塔、创意馆等地标建筑，如今是市民休闲和亲子游玩的大型公园。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.3278, "lng": 109.0569}, "tags": ["公园", "亲子", "地标"], "suitable_for": ["家庭", "儿童", "老人"], "opening_hours": "08:00-18:00"},
    {"name": "乐华城欢乐世界", "category": "entertainment", "description": "西北地区最大的主题乐园之一，有过山车、激流勇进、水上乐园等多种刺激好玩的游乐设施，适合全家出游。", "rating": 4.2, "ticket_price_cny": 220, "location": {"lat": 34.4500, "lng": 108.9000}, "tags": ["主题乐园", "亲子", "刺激"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:30-18:00"},
    {"name": "西安音乐厅", "category": "entertainment", "description": "位于大唐不夜城核心区的专业音乐演出场馆，常年有交响乐、室内乐等高水准演出，是西安古典音乐爱好者的殿堂。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 34.2125, "lng": 108.9650}, "tags": ["音乐", "演出", "艺术"], "suitable_for": ["情侣", "独行"], "opening_hours": "以演出时间为准"},
    {"name": "西安美术馆", "category": "entertainment", "description": "大唐不夜城旁的专业美术展览馆，常年举办国内外当代艺术展览，是西安艺术爱好者和文艺青年的聚集地。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2140, "lng": 108.9655}, "tags": ["美术馆", "艺术", "展览"], "suitable_for": ["独行", "情侣"], "opening_hours": "10:00-18:00"},
    {"name": "陕西大剧院", "category": "entertainment", "description": "西北地区规模最大、设施最先进的大型演出场馆，歌剧、舞剧、话剧等轮番上演，建筑本身也是一件艺术品。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 34.2125, "lng": 108.9640}, "tags": ["剧院", "演出", "艺术"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "以演出时间为准"},
    {"name": "长安十二时辰主题街区", "category": "entertainment", "description": "以热门影视剧为IP打造的沉浸式唐风主题街区，可穿汉服、逛集市、看表演，沉浸式体验盛唐长安的市井生活。", "rating": 4.4, "ticket_price_cny": 128, "location": {"lat": 34.2143, "lng": 108.9645}, "tags": ["沉浸式体验", "汉服", "唐文化"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "永宁门《梦长安》演出", "category": "entertainment", "description": "在西安城墙南门（永宁门）上演的大型实景迎宾演出，以盛唐礼仪为主题，气势恢弘，是了解唐代文化的视听盛宴。", "rating": 4.5, "ticket_price_cny": 280, "location": {"lat": 34.2530, "lng": 108.9440}, "tags": ["实景演出", "唐文化", "夜间"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "20:00-21:00"},
    {"name": "华清宫《长恨歌》演出", "category": "entertainment", "description": "在华清宫骊山脚下上演的大型山水实景历史舞剧，以白居易长诗《长恨歌》为蓝本，讲述唐玄宗与杨贵妃的爱情故事，场面震撼。", "rating": 4.7, "ticket_price_cny": 298, "location": {"lat": 34.3589, "lng": 109.2069}, "tags": ["实景演出", "舞剧", "唐文化"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "20:10-21:20"},
    {"name": "骡马市步行街", "category": "shopping", "description": "西安市中心东大街附近的商业步行街，汇集了各类潮牌服饰、鞋帽配饰和特色小吃，是年轻人逛街的热门去处。", "rating": 4.0, "ticket_price_cny": 0, "location": {"lat": 34.2600, "lng": 108.9470}, "tags": ["购物", "步行街", "潮流"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "东大街", "category": "shopping", "description": "西安历史悠久的传统商业街，从钟楼到东门，沿街店铺林立，既有老字号也有现代品牌，承载着西安人的购物记忆。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 34.2605, "lng": 108.9500}, "tags": ["购物", "商业街", "老字号"], "suitable_for": ["情侣", "独行", "老人"], "opening_hours": "全天"},
    {"name": "小寨赛格", "category": "shopping", "description": "西安人气最旺的购物中心之一，拥有亚洲最长的室内扶梯，品牌齐全、美食荟萃，是年轻人购物的首选地。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2231, "lng": 108.9410}, "tags": ["购物中心", "美食", "品牌"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "开元商城", "category": "shopping", "description": "位于钟楼旁的老牌高端百货商场，地理位置绝佳，汇集国际国内一线品牌，是西安最早的现代化购物中心之一。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.2600, "lng": 108.9430}, "tags": ["购物", "地标", "品牌"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "SKP西安", "category": "shopping", "description": "位于永宁门旁的高端奢侈品购物中心，国际一线奢侈品牌云集，装修奢华大气，是西安顶级消费体验场所。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 34.2545, "lng": 108.9448}, "tags": ["奢侈品", "高端购物", "品牌"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "大悦城大雁塔店", "category": "shopping", "description": "紧邻大雁塔的时尚购物中心，楼顶观景平台可近距离欣赏大雁塔，集购物、餐饮、娱乐于一体。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2185, "lng": 108.9600}, "tags": ["购物中心", "美食", "地标"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "李家村万达", "category": "shopping", "description": "西安南郊的综合性购物广场，集购物、餐饮、电影院、KTV于一体，是周边居民和学生群体的消费娱乐中心。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 34.2435, "lng": 108.9555}, "tags": ["购物中心", "美食", "娱乐"], "suitable_for": ["情侣", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "万象天地", "category": "shopping", "description": "曲江新区的高端商业综合体，设计时尚、品牌丰富，有各种网红餐厅和潮流店铺，是城南新兴的购物休闲地标。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 34.2090, "lng": 108.9705}, "tags": ["购物中心", "网红", "品牌"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "大融城", "category": "shopping", "description": "位于北大街附近的时尚购物中心，品牌定位年轻化，餐饮和娱乐业态丰富，是年轻人喜爱的潮流消费目的地。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.2650, "lng": 108.9480}, "tags": ["购物中心", "潮流", "美食"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "大唐西市", "category": "shopping", "description": "复原唐代西市遗址的商业文化综合体，有古玩城、丝绸之路风情街和博物馆，集购物、文化、旅游于一体。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 34.2558, "lng": 108.9112}, "tags": ["购物", "文化", "古玩"], "suitable_for": ["家庭", "独行", "老人"], "opening_hours": "10:00-22:00"},
]


def seed():
    print(f"Seeding {len(XIAN_ATTRACTIONS)} Xi'an attractions...")
    store = get_chroma_store()

    existing = store.search_attractions("西安", city="西安", k=1)
    if existing:
        print(f"Xi'an data already exists ({store.collection_count('attractions')} total). Delete first if re-seed.")
        return

    # Add city field to each attraction
    for a in XIAN_ATTRACTIONS:
        a["city"] = "西安"

    n = store.add_attractions(XIAN_ATTRACTIONS)
    print(f"Done! Added {n} attractions to ChromaDB.")

    # Verify
    print(f"Collection count: {store.collection_count('attractions')}")

    # Quick semantic search test
    results = store.search_attractions("适合老人的自然景点", city="西安", k=3)
    print(f"\nSemantic search test '适合老人的自然景点':")
    for r in results:
        print(f"  - {r['name']} (score: {r['_chroma_score']:.3f})")


if __name__ == "__main__":
    seed()
