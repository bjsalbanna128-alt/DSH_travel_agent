"""Seed Beijing attractions into ChromaDB for semantic search."""

import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_beijing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.embeddings import get_embedding_provider
from app.services.chroma_store import get_chroma_store

BEIJING_ATTRACTIONS = [
    # ===== cultural (18) =====
    {"name": "故宫", "category": "cultural", "description": "世界上现存规模最大、保存最完整的木质结构古建筑群，明清两代的皇家宫殿，收藏有大量珍贵文物和艺术品。", "rating": 4.8, "ticket_price_cny": 60, "location": {"lat": 39.9163, "lng": 116.3972}, "tags": ["世界遗产", "古建筑", "皇家", "博物馆"], "suitable_for": ["家庭", "情侣", "老人", "独行"], "opening_hours": "08:30-17:00"},
    {"name": "天坛", "category": "cultural", "description": "明清皇帝祭天祈谷的场所，祈年殿是北京标志性建筑之一，回音壁和三音石巧妙运用声学原理令人称奇。", "rating": 4.7, "ticket_price_cny": 35, "location": {"lat": 39.8822, "lng": 116.4066}, "tags": ["世界遗产", "古建筑", "皇家", "祈福"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "06:00-21:00"},
    {"name": "颐和园", "category": "cultural", "description": "中国现存规模最大的皇家园林，万寿山和昆明湖构成绝美山水画卷，长廊彩绘举世闻名，四季皆宜游览。", "rating": 4.7, "ticket_price_cny": 30, "location": {"lat": 39.9999, "lng": 116.2754}, "tags": ["世界遗产", "皇家园林", "湖泊", "古建筑"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "06:30-18:00"},
    {"name": "雍和宫", "category": "cultural", "description": "北京最大的藏传佛教寺院，曾是雍正皇帝的行宫，万福阁内白檀木大佛高26米，香火极为旺盛。", "rating": 4.6, "ticket_price_cny": 25, "location": {"lat": 39.9474, "lng": 116.4175}, "tags": ["佛教", "古建筑", "祈福", "皇家"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "孔庙和国子监", "category": "cultural", "description": "元明清三代国家最高学府和祭祀孔子的场所，古柏参天，碑林众多，是感受中国古代教育文化的圣地。", "rating": 4.5, "ticket_price_cny": 30, "location": {"lat": 39.9455, "lng": 116.4180}, "tags": ["儒家文化", "古建筑", "历史", "碑林"], "suitable_for": ["家庭", "老人", "独行", "儿童"], "opening_hours": "08:30-17:00"},
    {"name": "恭王府", "category": "cultural", "description": "清代规模最大的王府建筑群，曾是大贪官和珅的府邸，后为恭亲王奕訢住所，后花园精美绝伦。", "rating": 4.6, "ticket_price_cny": 40, "location": {"lat": 39.9366, "lng": 116.3835}, "tags": ["古建筑", "皇家", "园林", "历史"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "08:30-17:00"},
    {"name": "北海公园", "category": "cultural", "description": "中国现存最古老的皇家园林之一，白塔是标志性景观，歌曲让我们荡起双桨的灵感来源地。", "rating": 4.5, "ticket_price_cny": 10, "location": {"lat": 39.9245, "lng": 116.3893}, "tags": ["皇家园林", "湖泊", "古建筑", "划船"], "suitable_for": ["家庭", "情侣", "老人", "儿童"], "opening_hours": "06:30-21:00"},
    {"name": "景山公园", "category": "cultural", "description": "位于北京中轴线上的皇家园林，登上万春亭可俯瞰故宫全景和北京中轴线，日落时分的景色尤为壮观。", "rating": 4.5, "ticket_price_cny": 2, "location": {"lat": 39.9225, "lng": 116.3966}, "tags": ["皇家园林", "观景", "中轴线", "拍照"], "suitable_for": ["家庭", "情侣", "老人", "独行"], "opening_hours": "06:30-21:00"},
    {"name": "圆明园", "category": "cultural", "description": "清代大型皇家园林遗址，曾被誉为万园之园，大水法遗址是沧桑历史的见证，荷花园景色优美。", "rating": 4.5, "ticket_price_cny": 25, "location": {"lat": 40.0082, "lng": 116.2983}, "tags": ["遗址", "皇家园林", "历史", "荷花"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "07:00-19:00"},
    {"name": "明十三陵", "category": "cultural", "description": "明朝十三位皇帝的陵墓群，定陵地宫已发掘开放可入内参观，神路石像生气势恢宏雕刻精美。", "rating": 4.4, "ticket_price_cny": 60, "location": {"lat": 40.2542, "lng": 116.2267}, "tags": ["世界遗产", "皇家陵墓", "历史", "古建筑"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:30-17:00"},
    {"name": "天安门广场", "category": "cultural", "description": "世界上最大的城市中心广场，有人民英雄纪念碑和毛主席纪念堂，每天清晨的升旗仪式庄严神圣。", "rating": 4.6, "ticket_price_cny": 0, "location": {"lat": 39.9054, "lng": 116.3976}, "tags": ["城市地标", "广场", "升旗", "爱国教育"], "suitable_for": ["家庭", "老人", "儿童", "独行"], "opening_hours": "全天"},
    {"name": "钟楼和鼓楼", "category": "cultural", "description": "北京中轴线北端的地标建筑，钟鼓楼曾是古代报时中心，登楼可俯瞰什刹海和胡同风貌。", "rating": 4.4, "ticket_price_cny": 30, "location": {"lat": 39.9405, "lng": 116.3950}, "tags": ["古建筑", "中轴线", "观景", "胡同"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "09:00-17:00"},
    {"name": "大栅栏", "category": "cultural", "description": "北京最古老的传统商业街之一，有同仁堂、瑞蚨祥等百年老字号，充满了老北京的市井气息。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.8952, "lng": 116.3958}, "tags": ["历史文化", "老字号", "购物", "胡同"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "全天"},
    {"name": "南锣鼓巷", "category": "cultural", "description": "北京最著名的胡同街区，汇集文创小店、特色咖啡馆和传统小吃，是体验老北京胡同文化的好去处。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 39.9379, "lng": 116.4043}, "tags": ["胡同", "文创", "美食", "拍照"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "全天"},
    {"name": "什刹海", "category": "cultural", "description": "由前海、后海、西海组成的北京内城最大水域，周边胡同和王府众多，夏天可划船冬天可滑冰。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 39.9370, "lng": 116.3875}, "tags": ["湖泊", "胡同", "划船", "滑冰"], "suitable_for": ["情侣", "家庭", "独行"], "opening_hours": "全天"},
    {"name": "烟袋斜街", "category": "cultural", "description": "什刹海旁的一条古老斜街，因形似烟袋而得名，遍布特色小店和手工艺品铺子，适合悠闲漫步。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 39.9385, "lng": 116.3933}, "tags": ["胡同", "手工艺", "购物", "漫步"], "suitable_for": ["情侣", "独行"], "opening_hours": "全天"},
    {"name": "前门大街", "category": "cultural", "description": "北京中轴线上的百年商业街，明清时期的御道，两侧建筑中西合璧，铛铛车是独特体验。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.8971, "lng": 116.3977}, "tags": ["历史文化", "购物", "老字号", "建筑"], "suitable_for": ["家庭", "老人", "情侣"], "opening_hours": "全天"},
    {"name": "国家博物馆", "category": "cultural", "description": "世界上单体建筑面积最大的博物馆，馆藏文物超过140万件，古代中国基本陈列是必看展览。", "rating": 4.7, "ticket_price_cny": 0, "location": {"lat": 39.9051, "lng": 116.4013}, "tags": ["博物馆", "历史", "文物", "国宝"], "suitable_for": ["家庭", "老人", "独行", "儿童"], "opening_hours": "09:00-17:00"},
    # ===== natural (12) =====
    {"name": "八达岭长城", "category": "natural", "description": "万里长城最著名和保存最完好的段落，不到长城非好汉指的便是这里，适合首次来北京的游客。", "rating": 4.7, "ticket_price_cny": 40, "location": {"lat": 40.3597, "lng": 116.0206}, "tags": ["世界遗产", "长城", "登山", "摄影"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "06:30-19:00"},
    {"name": "慕田峪长城", "category": "natural", "description": "外国人最爱的长城段落，植被覆盖率达96%以上，相比八达岭人更少景色更原始，有滑道下山体验。", "rating": 4.6, "ticket_price_cny": 45, "location": {"lat": 40.4376, "lng": 116.5619}, "tags": ["世界遗产", "长城", "登山", "滑道"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "07:30-17:30"},
    {"name": "香山公园", "category": "natural", "description": "北京赏红叶的首选之地，每年秋季满山黄栌树叶变红蔚为壮观，还有双清别墅等历史建筑。", "rating": 4.5, "ticket_price_cny": 10, "location": {"lat": 39.9926, "lng": 116.1874}, "tags": ["红叶", "登山", "自然风光", "历史"], "suitable_for": ["家庭", "情侣", "老人"], "opening_hours": "06:00-18:30"},
    {"name": "奥林匹克森林公园", "category": "natural", "description": "北京最大的城市公园，2008年奥运会配套项目，有湿地、森林和湖泊，是跑步和骑行爱好者的天堂。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 40.0184, "lng": 116.3919}, "tags": ["公园", "跑步", "骑行", "自然"], "suitable_for": ["家庭", "儿童", "独行", "情侣"], "opening_hours": "06:00-21:00"},
    {"name": "北京动物园", "category": "natural", "description": "中国最早的动物园之一，有大熊猫馆、海洋馆和狮虎山，是北京亲子游的经典去处。", "rating": 4.3, "ticket_price_cny": 15, "location": {"lat": 39.9424, "lng": 116.3371}, "tags": ["动物园", "亲子", "熊猫", "海洋馆"], "suitable_for": ["家庭", "儿童"], "opening_hours": "07:30-18:00"},
    {"name": "北京植物园", "category": "natural", "description": "拥有亚洲最大的热带植物展览温室，春季桃花节和秋季菊花展最受欢迎，卧佛寺也坐落其中。", "rating": 4.4, "ticket_price_cny": 5, "location": {"lat": 40.0028, "lng": 116.2019}, "tags": ["植物园", "赏花", "温室", "自然"], "suitable_for": ["家庭", "老人", "情侣", "儿童"], "opening_hours": "06:00-19:00"},
    {"name": "玉渊潭公园", "category": "natural", "description": "北京最著名的赏樱胜地，每年三月底四月初樱花盛开时节游人如织，湖面宽阔可泛舟。", "rating": 4.4, "ticket_price_cny": 2, "location": {"lat": 39.9178, "lng": 116.3186}, "tags": ["樱花", "公园", "划船", "赏花"], "suitable_for": ["家庭", "情侣", "老人", "儿童"], "opening_hours": "06:00-21:30"},
    {"name": "紫竹院公园", "category": "natural", "description": "以竹景为主题的江南园林式公园，园内种植各类竹子数十种，是闹市中一处清幽雅致的去处。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 39.9450, "lng": 116.3263}, "tags": ["公园", "竹林", "湖泊", "休闲"], "suitable_for": ["家庭", "老人", "儿童"], "opening_hours": "06:00-21:00"},
    {"name": "朝阳公园", "category": "natural", "description": "北京四环内最大的城市公园，拥有广阔的湖面和草坪，经常举办音乐节和大型户外活动。", "rating": 4.3, "ticket_price_cny": 5, "location": {"lat": 39.9462, "lng": 116.4785}, "tags": ["公园", "音乐节", "湖泊", "野餐"], "suitable_for": ["家庭", "情侣", "儿童", "独行"], "opening_hours": "06:00-22:00"},
    {"name": "百望山", "category": "natural", "description": "距市中心最近的森林公园之一，山路平缓适合轻徒步，山顶可远眺北京全景和中关村天际线。", "rating": 4.1, "ticket_price_cny": 6, "location": {"lat": 40.0302, "lng": 116.2552}, "tags": ["登山", "森林", "观景", "徒步"], "suitable_for": ["独行", "情侣", "家庭"], "opening_hours": "06:00-18:00"},
    {"name": "龙庆峡", "category": "natural", "description": "京郊小三峡之称的峡谷景区，夏季可乘船穿行峡谷间，冬季有大型冰灯艺术节。", "rating": 4.3, "ticket_price_cny": 40, "location": {"lat": 40.5445, "lng": 116.0078}, "tags": ["峡谷", "划船", "冰灯", "自然风光"], "suitable_for": ["家庭", "情侣", "儿童"], "opening_hours": "07:30-16:30"},
    {"name": "妙峰山", "category": "natural", "description": "北京著名的宗教和民俗名山，有华北规模最大的娘娘庙会，春季玫瑰谷的花海美不胜收。", "rating": 4.2, "ticket_price_cny": 40, "location": {"lat": 40.0698, "lng": 116.0198}, "tags": ["登山", "庙会", "玫瑰", "宗教"], "suitable_for": ["家庭", "老人", "独行"], "opening_hours": "08:00-17:00"},
    # ===== entertainment (10) =====
    {"name": "798艺术区", "category": "entertainment", "description": "由旧电子工业老厂区改造的艺术园区，有画廊、设计工作室、时尚咖啡馆和涂鸦墙，是文艺青年圣地。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 39.9837, "lng": 116.4954}, "tags": ["艺术", "画廊", "拍照", "文创"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-18:00"},
    {"name": "三里屯太古里", "category": "entertainment", "description": "北京最时尚的开放式商业街区，汇集国际品牌旗舰店、网红餐厅和潮流夜店，年轻人聚集地。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 39.9325, "lng": 116.4583}, "tags": ["购物", "夜生活", "美食", "潮流"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "后海酒吧街", "category": "entertainment", "description": "什刹海后海沿岸的酒吧聚集区，湖边喝酒听歌别有风味，是北京最具代表性的夜生活地标之一。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9389, "lng": 116.3880}, "tags": ["酒吧", "夜生活", "音乐", "湖景"], "suitable_for": ["情侣", "独行"], "opening_hours": "18:00-02:00"},
    {"name": "北京欢乐谷", "category": "entertainment", "description": "北京最大的主题乐园，有过山车、激流勇进等刺激项目和大型表演，分为七大主题区域。", "rating": 4.4, "ticket_price_cny": 299, "location": {"lat": 39.8704, "lng": 116.4977}, "tags": ["主题乐园", "过山车", "亲子", "刺激"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:30-22:00"},
    {"name": "中国科技馆", "category": "entertainment", "description": "中国最大的科技馆，有丰富的互动式科学展品、球幕影院和儿童科学乐园，寓教于乐的绝佳场所。", "rating": 4.6, "ticket_price_cny": 30, "location": {"lat": 39.9672, "lng": 116.3930}, "tags": ["科技", "亲子", "互动", "教育"], "suitable_for": ["家庭", "儿童"], "opening_hours": "09:30-17:00"},
    {"name": "北京天文馆", "category": "entertainment", "description": "中国最早的天文科普场馆，拥有最先进的天象厅和宇宙剧场，仰望星空的奇幻之旅。", "rating": 4.4, "ticket_price_cny": 10, "location": {"lat": 39.9427, "lng": 116.3385}, "tags": ["天文", "科普", "亲子", "球幕"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "09:30-16:30"},
    {"name": "首都博物馆", "category": "entertainment", "description": "展示北京历史文化和城市建设成就的综合博物馆，馆藏丰富，建筑设计现代感十足。", "rating": 4.5, "ticket_price_cny": 0, "location": {"lat": 39.9053, "lng": 116.3457}, "tags": ["博物馆", "历史", "建筑", "文化"], "suitable_for": ["家庭", "老人", "独行", "儿童"], "opening_hours": "09:00-17:00"},
    {"name": "国家大剧院", "category": "entertainment", "description": "北京地标性文化艺术殿堂，巨型钛金属穹顶建筑被称为巨蛋，常年上演歌剧、芭蕾和交响乐。", "rating": 4.6, "ticket_price_cny": 30, "location": {"lat": 39.9036, "lng": 116.3894}, "tags": ["建筑", "演出", "歌剧", "地标"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "09:00-17:00"},
    {"name": "蓝色港湾", "category": "entertainment", "description": "欧式风格的湖畔商业休闲区，集购物、餐饮和娱乐于一体，冬季灯光节美轮美奂极受欢迎。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9530, "lng": 116.4738}, "tags": ["购物", "餐饮", "灯光节", "湖畔"], "suitable_for": ["情侣", "家庭", "儿童"], "opening_hours": "10:00-22:00"},
    {"name": "中国电影博物馆", "category": "entertainment", "description": "世界上最大的国家级电影专业博物馆，回顾中国电影百年发展史，有巨幕IMAX影院和大量互动展项。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9960, "lng": 116.5197}, "tags": ["电影", "博物馆", "IMAX", "亲子"], "suitable_for": ["家庭", "儿童", "情侣", "独行"], "opening_hours": "09:00-16:30"},
    # ===== shopping (10) =====
    {"name": "王府井", "category": "shopping", "description": "北京最有名的商业街，百年历史的老字号与现代化商场并存，小吃街和百货大楼是必逛之处。", "rating": 4.4, "ticket_price_cny": 0, "location": {"lat": 39.9148, "lng": 116.4150}, "tags": ["购物", "美食", "老字号", "步行街"], "suitable_for": ["家庭", "情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "西单", "category": "shopping", "description": "北京年轻人最爱的购物商圈，大悦城、君太百货等大型商场林立，时尚品牌和美食选择极多。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9118, "lng": 116.3735}, "tags": ["购物", "商场", "时尚", "美食"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "国贸CBD", "category": "shopping", "description": "北京中央商务区核心地带，拥有国贸商城等高端购物中心，云集奢侈品牌、五星级酒店和顶级写字楼。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9088, "lng": 116.4605}, "tags": ["购物", "奢侈品", "高端", "商务"], "suitable_for": ["情侣", "独行"], "opening_hours": "10:00-22:00"},
    {"name": "潘家园旧货市场", "category": "shopping", "description": "中国最大的古玩和旧货交易市场，字画、瓷器、玉器应有尽有，是寻宝和感受北京民俗的好去处。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.8736, "lng": 116.4597}, "tags": ["古玩", "旧货", "淘宝", "民俗"], "suitable_for": ["独行", "老人", "家庭"], "opening_hours": "08:30-18:00"},
    {"name": "琉璃厂文化街", "category": "shopping", "description": "北京著名的传统文化街，以荣宝斋为代表的笔墨纸砚和古籍书店聚集，文人墨客的朝圣之地。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.8940, "lng": 116.3865}, "tags": ["文房四宝", "古籍", "书画", "传统文化"], "suitable_for": ["独行", "老人", "家庭"], "opening_hours": "09:00-18:00"},
    {"name": "秀水街", "category": "shopping", "description": "北京著名的外贸服装市场，以丝绸、定制服装和纪念品闻名，外国游客最爱的砍价购物地。", "rating": 4.1, "ticket_price_cny": 0, "location": {"lat": 39.9142, "lng": 116.4525}, "tags": ["服装", "丝绸", "砍价", "纪念品"], "suitable_for": ["情侣", "独行"], "opening_hours": "09:00-21:00"},
    {"name": "世贸天阶", "category": "shopping", "description": "北京CBD核心地段的时尚购物中心，拥有亚洲最大的LED天幕——全北京向上看，夜晚灯光璀璨。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 39.9195, "lng": 116.4571}, "tags": ["购物", "LED天幕", "夜景", "时尚"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "华熙LIVE", "category": "shopping", "description": "五棵松体育馆旁的大型综合商业体，集餐饮、购物、娱乐和演出于一体，京城潮流新地标。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9077, "lng": 116.2765}, "tags": ["购物", "美食", "演出", "潮流"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
    {"name": "合生汇", "category": "shopping", "description": "朝阳区大型家庭购物中心，有超过500家店铺、大型超市、影院和丰富的儿童娱乐设施。", "rating": 4.2, "ticket_price_cny": 0, "location": {"lat": 39.8945, "lng": 116.5122}, "tags": ["购物", "亲子", "影院", "餐饮"], "suitable_for": ["家庭", "儿童", "情侣"], "opening_hours": "10:00-22:00"},
    {"name": "东方新天地", "category": "shopping", "description": "王府井商圈内的大型商业综合体，连接王府井和东单，国际品牌和高端餐饮云集的地下商城。", "rating": 4.3, "ticket_price_cny": 0, "location": {"lat": 39.9131, "lng": 116.4178}, "tags": ["购物", "商场", "高端", "地下商城"], "suitable_for": ["情侣", "独行", "家庭"], "opening_hours": "10:00-22:00"},
]


def seed():
    print(f"Seeding {len(BEIJING_ATTRACTIONS)} Beijing attractions...")
    store = get_chroma_store()

    existing = store.search_attractions("北京", city="北京", k=1)
    if existing:
        print(f"Beijing data already exists ({store.collection_count('attractions')} total). Delete first if re-seed.")
        return

    # Add city field to each attraction
    for a in BEIJING_ATTRACTIONS:
        a["city"] = "北京"

    n = store.add_attractions(BEIJING_ATTRACTIONS)
    print(f"Done! Added {n} attractions to ChromaDB.")

    # Verify
    print(f"Collection count: {store.collection_count('attractions')}")

    # Quick semantic search test
    results = store.search_attractions("适合亲子的文化景点", city="北京", k=3)
    print(f"\nSemantic search test '适合亲子的文化景点':")
    for r in results:
        print(f"  - {r['name']} (score: {r['_chroma_score']:.3f})")


if __name__ == "__main__":
    seed()
