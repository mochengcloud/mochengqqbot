import random
import hashlib
import time
import json
from datetime import date, datetime
from typing import Dict, Optional
from pathlib import Path

from core import on_command, on_message, CommandArg, SUPERUSER, FinishedException
from core.menu_registry import menu_registry
from core.onebot import Bot, GroupMessageEvent, Message, MessageSegment

from log_manager import log_manager
from plugins.utils import reply_msg

# ==================== 数据池 ====================

LUCK_LEVELS = [
    ("大凶", 0, 20, "🔴"),
    ("小凶", 21, 40, "🟠"),
    ("末吉", 41, 55, "🟡"),
    ("小吉", 56, 70, "🟢"),
    ("中吉", 71, 85, "🔵"),
    ("大吉", 86, 95, "🟣"),
    ("大圆满", 96, 100, "🌟"),
]

FORTUNE_TEXTS = [
    "山重水复疑无路，柳暗花明又一村。",
    "长风破浪会有时，直挂云帆济沧海。",
    "沉舟侧畔千帆过，病树前头万木春。",
    "莫愁前路无知己，天下谁人不识君。",
    "春风得意马蹄疾，一日看尽长安花。",
    "人生得意须尽欢，莫使金樽空对月。",
    "天生我材必有用，千金散尽还复来。",
    "宝剑锋从磨砺出，梅花香自苦寒来。",
    "千淘万漉虽辛苦，吹尽狂沙始到金。",
    "海内存知己，天涯若比邻。",
    "愿得一心人，白首不相离。",
    "但愿人长久，千里共婵娟。",
    "会当凌绝顶，一览众山小。",
    "不畏浮云遮望眼，自缘身在最高层。",
    "路漫漫其修远兮，吾将上下而求索。",
    "老当益壮，宁移白首之心？穷且益坚，不坠青云之志。",
    "业精于勤，荒于嬉；行成于思，毁于随。",
    "学而不思则罔，思而不学则殆。",
    "温故而知新，可以为师矣。",
    "三人行，必有我师焉。",
]

LOTTERY_STICKS = [
    ("上上签", "🌸 上上签：万事如意，心想事成！"),
    ("上上签", "🌸 上上签：紫气东来，鸿运当头！"),
    ("上上签", "🌸 上上签：天官赐福，百无禁忌！"),
    ("上吉签", "🌟 上吉签：春风得意，前程似锦！"),
    ("上吉签", "🌟 上吉签：吉星高照，好运连连！"),
    ("上吉签", "🌟 上吉签：心想事成，万事亨通！"),
    ("中吉签", "✨ 中吉签：一帆风顺，两全其美！"),
    ("中吉签", "✨ 中吉签：诸事顺遂，渐入佳境！"),
    ("中吉签", "✨ 中吉签：循序渐进，必有所成！"),
    ("中吉签", "✨ 中吉签：和和气气，喜气洋洋！"),
    ("中平签", "🌿 中平签：平平淡淡，顺其自然。"),
    ("中平签", "🌿 中平签：守得云开，方见月明。"),
    ("中平签", "🌿 中平签：不急不躁，水到渠成。"),
    ("中平签", "🌿 中平签：谋事在人，成事在天。"),
    ("下吉签", "☁️ 下吉签：略有坎坷，小有波折。"),
    ("下吉签", "☁️ 下吉签：一着不慎，需防小人。"),
    ("下凶签", "🌧️ 下凶签：一时困顿，宜静不宜动。"),
    ("下凶签", "🌧️ 下凶签：诸事不宜，宜守不宜攻。"),
    ("下凶签", "🌧️ 下凶签：风雨欲来，宜早做准备。"),
    ("下下签", "⚡ 下下签：诸事不顺，需避锋芒！"),
]

PRAISES = [
    "你的颜值简直可以申请世界文化遗产！",
    "你的才华横溢得就像打翻了银河系！",
    "你的笑容比春天的阳光还要温暖！",
    "你的智商已经突破了大气层！",
    "你的存在本身就是这个世界的美好证明！",
    "你一定是女娲精心捏造的那一款！",
    "你的气质比故宫还要有底蕴！",
    "你的眼睛里有星辰大海！",
    "你走路带风的样子像极了超模！",
    "你的声音比百灵鸟还要动听！",
    "你就是传说中的天选之子吧！",
    "你的善良让你的光芒万丈！",
    "你认真的时候帅/美得不像人类！",
    "你的微信头像都散发着艺术气息！",
    "你的朋友圈简直就是艺术品展览！",
    "你的幽默感可以去开专场脱口秀！",
    "你的品味比米其林三星还要高级！",
    "你简直就是行走的荷尔蒙！",
    "你的气场强大到让维密超模都自愧不如！",
    "如果说颜值是罪，你已经罪不可赦！",
    "你的每一个细胞都在散发着魅力！",
    "你一定是上帝最得意的作品！",
    "你的存在拉高了人类的平均颜值！",
    "你简直就是人间理想和星光！",
    "你的魅力让月亮都害羞地躲进了云里！",
    "你的才华和颜值成正比！",
    "你绝对是爸妈最成功的作品！",
    "你的穿搭品味可以引领时尚潮流！",
    "你笑起来世界都亮了！",
    "你就是人间四月天！",
]

POISON_SOUP = [
    "你抱得动你自己吗？",
    "你以为你是怀才不遇，其实你是怀才不够。",
    "失败并不可怕，可怕的是你还相信这句话。",
    "上帝为你关上一扇门的同时，还会顺便把窗户也关上。",
    "你全力做到最好，可能还不如别人随便搞搞。",
    "小时候你以为自己是主角，长大后发现你是跑龙套的。",
    "你丑得很有特色，可惜是丑的特色。",
    "别灰心，人生就是这样起起落落落落落落落落。",
    "你以为的极限，弄不好只是别人的起点。",
    "你不是一无所有，你还有病。",
    "努力不一定成功，但不努力一定很轻松。",
    "咸鱼翻身了还是咸鱼。",
    "比上不足，比下有余，但你就是那个下。",
    "你的工资水平已经成功拖累了国家GDP。",
    "你并没有被生活磨平棱角，只是因为你本来就是圆的。",
    "生活的暴击让你变成了一个更好…的废柴。",
    "你身上唯一能滚动的，只有肚子上的肉。",
    "你的钱包和你的脸一样干净。",
    "所有你以为的幸运，都是别人努力得来的，不关你事。",
    "别再说自己懒了，你明明就是菜。",
    "间歇性踌躇满志，持续性混吃等死。",
    "你所谓的努力，只是把原来玩手机的时间改成了发呆。",
    "脱贫的方法有很多，但你都用不上。",
    "你的人生就像保温杯，啥都保温但啥都烫嘴。",
    "你不是社恐，你是社丑。",
    "别人是宝藏，你是五毛钱一包的辣条。",
    "你以为自己是千里马，其实你是那头驴。",
    "你的单身不是因为缘分未到，而是因为丑。",
    "你所谓的佛系，其实就是懒和丧。",
    "别让生活耗尽了你的耐心和梦想，你还有…算了你啥也没有。",
]

RIDDLES = [
    ("什么动物最怕水？", "雪人（因为雪人遇到水就化了）"),
    ("什么东西越洗越脏？", "水（洗东西的水会变脏）"),
    ("什么书不能看？", "说明书（书=输，不能输）"),
    ("什么人生病从来不看医生？", "盲人（因为看不见医生）"),
    ("什么东西越削越大？", "坑（越挖越大）"),
    ("什么东西早上四条腿，中午两条腿，晚上三条腿？", "人（婴儿爬/成人走/老人拄拐）"),
    ("什么杯子不能装水？", "奖杯（奖杯不装水）"),
    ("什么东西你越给它，它越瘦？", "洞（越挖越大，剩下的地方越少）"),
    ("什么球不能踢？", "眼球"),
    ("什么门永远关不上？", "球门（足球门没有门扇）"),
    ("什么东西一直走却永远在原地？", "钟表/时钟"),
    ("什么动物天天熬夜？", "熊猫（因为黑眼圈）"),
    ("什么东西不拍打的时候很硬，拍打的时候很软？", "屁股"),
    ("什么东西看起来是绿的，打开是红的，吃起来是甜的？", "西瓜"),
    ("什么猫用两只脚走路？", "机器猫/哆啦A梦"),
    ("什么车最长？", "堵车/塞车"),
    ("什么东西一年比一年更大？", "年龄"),
    ("什么鱼不能吃？", "木鱼"),
    ("什么蛋不能吃？", "脸蛋/零蛋"),
    ("什么东西你越用它越亮？", "灯泡"),
    ("什么鼠最爱干净？", "浣熊（虽然叫熊但像鼠一样爱洗东西）"),
    ("什么东西不用时是白的，用时是黑的？", "粉笔（写黑板上）"),
    ("什么鬼天天飘在空中？", "烟鬼（抽烟的烟雾）"),
    ("什么花没有枝？", "雪花/浪花/火花"),
    ("什么东西说大就大说小就小？", "气球"),
    ("什么东西越热越出来？", "汗"),
    ("什么马不吃草？", "海马/木马/电马"),
    ("什么人从来不洗脸？", "泥人"),
    ("什么东西满了就空？", "垃圾桶（满了被倒空）"),
    ("什么果不能吃？", "如果/结果"),
    ("什么牛不耕田？", "蜗牛/海牛"),
    ("什么虎不吃肉？", "壁虎/纸老虎"),
    ("什么山不能爬？", "假山/人山人海"),
    ("什么海没有鱼？", "脑海/辞海"),
    ("什么水不能喝？", "薪水/胶水/墨水"),
    ("什么路不能走？", "思路/电路/铁路（不是用走的）"),
    ("什么车最怕水？", "火车（火车怕水？其实是洒水车？）"),
    ("什么东西越剪越短？", "绳子（其实越剪越短对）"),
    ("什么角不是角？", "五角钱的角/配角"),
    ("什么线不能缝衣服？", "光线/电线"),
    ("什么人最会弄虚作假？", "魔术师"),
    ("什么事情一个人做不了？", "做梦（别人不能替你）"),
    ("什么东西一人一个？", "影子"),
    ("什么蛋糕不能吃？", "肥皂蛋糕/蜡烛蛋糕"),
    ("什么东西看不见摸不着但很重要？", "空气/时间/感情"),
    ("什么球会自己长大？", "地球/乒乓球不会，是气球！"),
    ("什么东西越分越少？", "时间/蛋糕"),
    ("什么东西有头无脚？", "针/钉子/筷子"),
    ("什么东西有脚无头？", "桌子/椅子/床"),
    ("什么东西越晒越湿？", "冰（越晒越融化越湿）"),
]

TAROT_CARDS = [
    ("愚者", "正位", "新的开始、冒险、天真、无限可能"),
    ("愚者", "逆位", "鲁莽、冒险失敗、不成熟、停滞"),
    ("魔术师", "正位", "创造力、自信、技能、资源整合"),
    ("魔术师", "逆位", "浪费天赋、欺骗、操控、不成熟"),
    ("女祭司", "正位", "直觉、智慧、内在知识、神秘"),
    ("女祭司", "逆位", "秘密泄露、过度压抑、肤浅、无知"),
    ("女皇", "正位", "丰收、繁荣、滋养、自然之美"),
    ("女皇", "逆位", "依赖、空虚、缺乏安全感、失去创造力"),
    ("皇帝", "正位", "权威、稳定、结构、父亲形象"),
    ("皇帝", "逆位", "专制、过度控制、软弱、缺乏纪律"),
    ("教皇", "正位", "传统、教育、信仰、精神导师"),
    ("教皇", "逆位", "教条、叛逆、不宽容、错误引导"),
    ("恋人", "正位", "爱情、和谐、选择、价值观一致"),
    ("恋人", "逆位", "分离、冲突、错误决定、价值观不合"),
    ("战车", "正位", "胜利、决心、意志力、控制"),
    ("战车", "逆位", "失控、侵略、挫折、缺乏方向"),
    ("力量", "正位", "勇气、力量、耐心、内在力量"),
    ("力量", "逆位", "软弱、不自信、恐惧、滥用力量"),
    ("隐士", "正位", "内省、智慧、追寻、独处"),
    ("隐士", "逆位", "孤独、自闭、愚蠢的决定、不合群"),
    ("命运之轮", "正位", "转变、命运、机遇、幸运"),
    ("命运之轮", "逆位", "厄运、意外变化、失控、坏运气"),
    ("正义", "正位", "公正、诚实、因果、法律"),
    ("正义", "逆位", "不公、欺骗、逃避责任、失衡"),
    ("倒吊人", "正位", "牺牲、放手、新视角、暂停"),
    ("倒吊人", "逆位", "拖延、拒绝牺牲、抗拒改变、停滞"),
    ("死神", "正位", "结束、转变、放下、重生"),
    ("死神", "逆位", "抗拒改变、停滞、恐惧、原地踏步"),
    ("节制", "正位", "平衡、适度、耐心、调和"),
    ("节制", "逆位", "失衡、冲突、过度、无耐心"),
    ("恶魔", "正位", "束缚、物质主义、诱惑、成瘾"),
    ("恶魔", "逆位", "觉醒、挣脱束缚、自由、重生"),
    ("高塔", "正位", "剧变、崩塌、觉醒、重建"),
    ("高塔", "逆位", "避免灾难、拖延改变、危机预警"),
    ("星星", "正位", "希望、灵感、平静、愈合"),
    ("星星", "逆位", "绝望、失望、缺乏信心、创意枯竭"),
    ("月亮", "正位", "幻觉、恐惧、潜意识、未知"),
    ("月亮", "逆位", "焦虑解除、面对恐惧、看清真相"),
    ("太阳", "正位", "快乐、成功、活力、积极"),
    ("太阳", "逆位", "短暂的快乐、过度乐观、拖延"),
    ("审判", "正位", "觉醒、决定、重生、召唤"),
    ("审判", "逆位", "自责、怀疑、拒绝觉醒、后悔"),
    ("世界", "正位", "完成、成就、圆满、旅行"),
    ("世界", "逆位", "未完成、拖延、不完美、缺乏方向"),
]

ACTION_VERBS_PAT = [
    "轻轻摸了摸{target}的头，温柔地说「乖~」",
    "伸手揉了揉{target}的头发，发出姨母笑",
    "用充满爱意的目光看着{target}，然后摸了摸头",
    "踮起脚摸了摸{target}的头，一脸宠溺",
]

ACTION_VERBS_SLAP = [
    "以迅雷不及掩耳之势扇了{target}一耳光！",
    "轻轻拍了一下{target}的脸颊，力道恰到好处",
    "一巴掌拍在{target}的脑门上，啪！",
    "反手就是一个大嘴巴子，{target}直接懵了",
]

ACTION_VERBS_GIFT = [
    "送给{target}一束美丽的鲜花🌹",
    "送了{target}一份精美礼物🎁，包装很用心",
    "递给{target}一杯热奶茶🧋温暖了心窝",
    "送了{target}一只可爱的玩偶🧸",
    "给{target}发了一个大红包🧧",
]

IDIOM_DB = [
    "一心一意", "一石二鸟", "三心二意", "四面八方", "五光十色",
    "六神无主", "七嘴八舌", "八仙过海", "九牛一毛", "十全十美",
    "百发百中", "千军万马", "万紫千红", "画蛇添足", "守株待兔",
    "掩耳盗铃", "亡羊补牢", "刻舟求剑", "叶公好龙", "狐假虎威",
    "井底之蛙", "对牛弹琴", "杯弓蛇影", "鹤立鸡群", "虎头蛇尾",
    "龙马精神", "鸡飞蛋打", "狗急跳墙", "鸟语花香", "风和日丽",
    "山清水秀", "春暖花开", "秋高气爽", "冰天雪地", "雷厉风行",
    "电闪雷鸣", "风雨同舟", "雪中送炭", "锦上添花", "花好月圆",
    "国色天香", "出水芙蓉", "闭月羞花", "沉鱼落雁", "才高八斗",
    "学富五车", "满腹经纶", "博古通今", "出口成章", "妙笔生花",
    "画龙点睛", "入木三分", "铁画银钩", "字里行间", "言简意赅",
    "语重心长", "苦口婆心", "推心置腹", "开诚布公", "肝胆相照",
    "情同手足", "风雨同舟", "同甘共苦", "患难与共", "亲密无间",
    "形影不离", "如胶似漆", "相敬如宾", "举案齐眉", "相濡以沫",
    "天长地久", "海枯石烂", "山盟海誓", "情投意合", "两情相悦",
    "一见钟情", "青梅竹马", "两小无猜", "心心相印", "心有灵犀",
    "不约而同", "不谋而合", "殊途同归", "异曲同工", "相辅相成",
    "相得益彰", "珠联璧合", "天作之合", "金玉良缘", "花好月圆",
    "安居乐业", "国泰民安", "繁荣昌盛", "蒸蒸日上", "欣欣向荣",
    "朝气蓬勃", "意气风发", "斗志昂扬", "生龙活虎", "精神抖擞",
    "神采奕奕", "容光焕发", "眉飞色舞", "喜笑颜开", "眉开眼笑",
    "心花怒放", "欢天喜地", "兴高采烈", "喜出望外", "乐不可支",
    "捧腹大笑", "哭笑不得", "啼笑皆非", "破涕为笑", "忍俊不禁",
    "哑然失笑", "嫣然一笑", "回眸一笑", "笑逐颜开", "喜上眉梢",
    "欣喜若狂", "欢欣鼓舞", "载歌载舞", "弹冠相庆", "额手称庆",
    "普天同庆", "举国欢腾", "万众欢腾", "热闹非凡", "人山人海",
    "车水马龙", "络绎不绝", "川流不息", "门庭若市", "座无虚席",
    "接踵而至", "纷至沓来", "络绎不绝", "络绎不绝", "源源不断",
    "日新月异", "突飞猛进", "一日千里", "与时俱进", "翻天覆地",
    "改天换地", "沧海桑田", "星移斗转", "光阴似箭", "日月如梭",
    "白驹过隙", "稍纵即逝", "转瞬即逝", "弹指之间", "瞬息万变",
    "惊天动地", "震天动地", "翻江倒海", "排山倒海", "气势磅礴",
    "波澜壮阔", "汹涌澎湃", "惊涛骇浪", "风起云涌", "风驰电掣",
    "雷厉风行", "大步流星", "健步如飞", "疾步如飞", "飞奔如箭",
]

# 会话状态
guess_number_sessions: Dict[str, dict] = {}
riddle_sessions: Dict[str, dict] = {}
idiom_sessions: Dict[str, dict] = {}

# ==================== 命令处理 ====================

def _get_daily_luck(user_id: int) -> int:
    h = hashlib.md5(f"{date.today().isoformat()}_{user_id}_luck".encode()).hexdigest()
    return int(h[:8], 16) % 101

# ---------- 骰子 ----------

roll_dice = on_command("骰子", priority=1, block=True)
roll_dice2 = on_command("掷骰子", priority=1, block=True)

@roll_dice.handle()
async def handle_roll_dice(event: GroupMessageEvent):
    d = random.randint(1, 6)
    faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    await roll_dice.finish(reply_msg(event, f"🎲 掷出了 {faces[d-1]} {d} 点！"))

@roll_dice2.handle()
async def handle_roll_dice2(event: GroupMessageEvent):
    d = random.randint(1, 6)
    faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    await roll_dice2.finish(reply_msg(event, f"🎲 掷出了 {faces[d-1]} {d} 点！"))

# ---------- 今日人品 ----------

daily_luck = on_command("今日人品", priority=1, block=True)
daily_luck2 = on_command("人品", priority=1, block=True)

@daily_luck.handle()
async def handle_daily_luck(event: GroupMessageEvent):
    score = _get_daily_luck(event.user_id)
    for name, lo, hi, icon in LUCK_LEVELS:
        if lo <= score <= hi:
            await daily_luck.finish(reply_msg(event, f"✨ 今日人品：{score}分 {icon}\n评级：{name}\n\n📜 {random.choice(FORTUNE_TEXTS)}"))

@daily_luck2.handle()
async def handle_daily_luck2(event: GroupMessageEvent):
    score = _get_daily_luck(event.user_id)
    for name, lo, hi, icon in LUCK_LEVELS:
        if lo <= score <= hi:
            await daily_luck2.finish(reply_msg(event, f"✨ 今日人品：{score}分 {icon}\n评级：{name}\n\n📜 {random.choice(FORTUNE_TEXTS)}"))

# ---------- 运势 ----------

fortune = on_command("运势", priority=1, block=True)

@fortune.handle()
async def handle_fortune(event: GroupMessageEvent):
    score = random.randint(0, 100)
    for name, lo, hi, icon in LUCK_LEVELS:
        if lo <= score <= hi:
            msg = f"🔮 今日运势\n━━━━━━━━\n运势评分：{score}分 {icon}\n等级：{name}\n\n💬 寄语：{random.choice(FORTUNE_TEXTS)}"
            await fortune.finish(reply_msg(event, msg))

# ---------- 抽签 ----------

lottery_stick = on_command("抽签", priority=1, block=True)

@lottery_stick.handle()
async def handle_lottery_stick(event: GroupMessageEvent):
    level, text = random.choice(LOTTERY_STICKS)
    await lottery_stick.finish(reply_msg(event, f"🎋 抽签结果\n━━━━━━━━\n{text}"))

# ---------- 塔罗牌 ----------

tarot = on_command("塔罗牌", priority=1, block=True)
tarot2 = on_command("抽塔罗", priority=1, block=True)

@tarot.handle()
async def handle_tarot(event: GroupMessageEvent):
    name, direction, meaning = random.choice(TAROT_CARDS)
    dir_icon = "▲" if direction == "正位" else "▼"
    await tarot.finish(reply_msg(event, f"🃏 塔罗牌\n━━━━━━━━\n{dir_icon} {name} · {direction}\n📖 释义：{meaning}"))

@tarot2.handle()
async def handle_tarot2(event: GroupMessageEvent):
    name, direction, meaning = random.choice(TAROT_CARDS)
    dir_icon = "▲" if direction == "正位" else "▼"
    await tarot2.finish(reply_msg(event, f"🃏 塔罗牌\n━━━━━━━━\n{dir_icon} {name} · {direction}\n📖 释义：{meaning}"))

# ---------- 彩虹屁 ----------

praise = on_command("彩虹屁", priority=1, block=True)
praise2 = on_command("夸我", priority=1, block=True)

@praise.handle()
async def handle_praise(event: GroupMessageEvent):
    text = random.choice(PRAISES)
    await praise.finish(reply_msg(event, f"💐 {text}"))

@praise2.handle()
async def handle_praise2(event: GroupMessageEvent):
    text = random.choice(PRAISES)
    await praise2.finish(reply_msg(event, f"💐 {text}"))

# ---------- 毒鸡汤 ----------

poison = on_command("毒鸡汤", priority=1, block=True)

@poison.handle()
async def handle_poison(event: GroupMessageEvent):
    text = random.choice(POISON_SOUP)
    await poison.finish(reply_msg(event, f"🍯 毒鸡汤\n━━━━━━━━\n{text}"))

# ---------- 动作指令 ----------

def _get_target(event: GroupMessageEvent) -> Optional[str]:
    for seg in event.message:
        if seg.type == "at":
            return str(seg.data.get("qq", ""))
    return None

headpat = on_command("摸头", priority=1, block=True)
headpat2 = on_command("摸摸头", priority=1, block=True)

@headpat.handle()
async def handle_headpat(event: GroupMessageEvent, args: Message = CommandArg()):
    target = _get_target(event)
    if not target:
        await headpat.finish(reply_msg(event, "请 @ 要摸头的人"))
    action = random.choice(ACTION_VERBS_PAT).replace("{target}", target)
    name = event.sender.card or event.sender.nickname or str(event.user_id)
    await headpat.finish(reply_msg(event, f"{name} {action}"))

@headpat2.handle()
async def handle_headpat2(event: GroupMessageEvent):
    target = _get_target(event)
    if not target:
        await headpat2.finish(reply_msg(event, "请 @ 要摸头的人"))
    action = random.choice(ACTION_VERBS_PAT).replace("{target}", target)
    name = event.sender.card or event.sender.nickname or str(event.user_id)
    await headpat2.finish(reply_msg(event, f"{name} {action}"))

slap = on_command("抽耳光", priority=1, block=True)

@slap.handle()
async def handle_slap(event: GroupMessageEvent):
    target = _get_target(event)
    if not target:
        await slap.finish(reply_msg(event, "请 @ 要抽的人"))
    action = random.choice(ACTION_VERBS_SLAP).replace("{target}", target)
    name = event.sender.card or event.sender.nickname or str(event.user_id)
    await slap.finish(reply_msg(event, f"{name} {action}"))

gift = on_command("送礼物", priority=1, block=True)
gift2 = on_command("送礼", priority=1, block=True)

@gift.handle()
async def handle_gift(event: GroupMessageEvent, args: Message = CommandArg()):
    target = _get_target(event)
    if not target:
        await gift.finish(reply_msg(event, "请 @ 要送礼的人"))
    action = random.choice(ACTION_VERBS_GIFT).replace("{target}", target)
    name = event.sender.card or event.sender.nickname or str(event.user_id)
    extra = args.extract_plain_text().strip()
    if extra:
        action += f"\n💌 附言：{extra}"
    await gift.finish(reply_msg(event, f"{name} {action}"))

@gift2.handle()
async def handle_gift2(event: GroupMessageEvent, args: Message = CommandArg()):
    target = _get_target(event)
    if not target:
        await gift2.finish(reply_msg(event, "请 @ 要送礼的人"))
    action = random.choice(ACTION_VERBS_GIFT).replace("{target}", target)
    name = event.sender.card or event.sender.nickname or str(event.user_id)
    extra = args.extract_plain_text().strip()
    if extra:
        action += f"\n💌 附言：{extra}"
    await gift2.finish(reply_msg(event, f"{name} {action}"))

# ---------- 猜谜语 ----------

riddle_start = on_command("猜谜语", priority=1, block=True)
riddle_answer = on_command("答案", priority=1, block=True)

@riddle_start.handle()
async def handle_riddle_start(event: GroupMessageEvent):
    q, a = random.choice(RIDDLES)
    gid = str(event.group_id)
    riddle_sessions[gid] = {"question": q, "answer": a, "time": time.time()}
    await riddle_start.finish(reply_msg(event, f"🧩 猜谜语\n━━━━━━━━\n{q}\n\n💡 发送「答案 你的答案」来回答"))

@riddle_answer.handle()
async def handle_riddle_answer(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    if gid not in riddle_sessions:
        await riddle_answer.finish(reply_msg(event, "当前没有进行中的谜语，发送「猜谜语」开始"))
    if time.time() - riddle_sessions[gid]["time"] > 180:
        del riddle_sessions[gid]
        await riddle_answer.finish(reply_msg(event, "⏰ 超时了！谜语已过期，发送「猜谜语」重新开始"))
    user_answer = args.extract_plain_text().strip()
    correct = riddle_sessions[gid]["answer"]
    if user_answer in correct or correct in user_answer:
        del riddle_sessions[gid]
        await riddle_answer.finish(reply_msg(event, f"✅ 答对了！\n谜底：{correct}"))
    else:
        await riddle_answer.finish(reply_msg(event, f"❌ 不对哦，再想想~\n💡 提示：谜底关键词"))

# ---------- 猜数字 ----------

guess_start = on_command("猜数字", priority=1, block=True)
guess_cmd = on_command("猜", priority=1, block=True)

@guess_start.handle()
async def handle_guess_start(event: GroupMessageEvent):
    gid = str(event.group_id)
    target = random.randint(1, 100)
    guess_number_sessions[gid] = {"target": target, "attempts": 0, "time": time.time(), "max_attempts": 10}
    await guess_start.finish(reply_msg(event, f"🔢 猜数字游戏开始！\n我已经想好了一个1~100之间的数字\n你有10次机会，发送「猜 数字」来猜猜看"))

@guess_cmd.handle()
async def handle_guess(event: GroupMessageEvent, args: Message = CommandArg()):
    gid = str(event.group_id)
    if gid not in guess_number_sessions:
        await guess_cmd.finish(reply_msg(event, "当前没有进行中的猜数字游戏，发送「猜数字」开始"))
    sess = guess_number_sessions[gid]
    if time.time() - sess["time"] > 300:
        del guess_number_sessions[gid]
        await guess_cmd.finish(reply_msg(event, f"⏰ 超时了！数字是 {sess['target']}，发送「猜数字」重新开始"))
    try:
        num = int(args.extract_plain_text().strip())
    except ValueError:
        await guess_cmd.finish(reply_msg(event, "请输入有效数字，例如「猜 50」"))
    sess["attempts"] += 1
    if num == sess["target"]:
        del guess_number_sessions[gid]
        await guess_cmd.finish(reply_msg(event, f"🎉 恭喜猜对了！就是 {num}！\n用了 {sess['attempts']} 次机会"))
    if sess["attempts"] >= sess["max_attempts"]:
        del guess_number_sessions[gid]
        await guess_cmd.finish(reply_msg(event, f"😅 10次都用完了！答案是 {sess['target']}"))
    hint = "大" if num > sess["target"] else "小"
    remaining = sess["max_attempts"] - sess["attempts"]
    await guess_cmd.finish(reply_msg(event, f"❌ {num} 比答案{hint}！还剩 {remaining} 次机会"))

# ---------- 随机CP ----------

random_cp = on_command("随机CP", priority=1, block=True)
random_cp2 = on_command("今日CP", priority=1, block=True)

@random_cp.handle()
async def handle_random_cp(bot: Bot, event: GroupMessageEvent):
    try:
        members = await bot.get_group_member_list(group_id=event.group_id)
        if len(members) < 2:
            await random_cp.finish(reply_msg(event, "群成员太少，无法配对…"))
        chosen = random.sample(members, 2)
        a = chosen[0].get("card") or chosen[0].get("nickname", str(chosen[0]["user_id"]))
        b = chosen[1].get("card") or chosen[1].get("nickname", str(chosen[1]["user_id"]))
        await random_cp.finish(reply_msg(event, f"💑 今日 CP\n━━━━━━━━\n{a} ❤️ {b}\n\n天生一对！"))
    except Exception as e:
        await random_cp.finish(reply_msg(event, f"获取群成员失败：{e}"))

@random_cp2.handle()
async def handle_random_cp2(bot: Bot, event: GroupMessageEvent):
    try:
        members = await bot.get_group_member_list(group_id=event.group_id)
        if len(members) < 2:
            await random_cp2.finish(reply_msg(event, "群成员太少，无法配对…"))
        chosen = random.sample(members, 2)
        a = chosen[0].get("card") or chosen[0].get("nickname", str(chosen[0]["user_id"]))
        b = chosen[1].get("card") or chosen[1].get("nickname", str(chosen[1]["user_id"]))
        await random_cp2.finish(reply_msg(event, f"💑 今日 CP\n━━━━━━━━\n{a} ❤️ {b}\n\n天生一对！"))
    except Exception as e:
        await random_cp2.finish(reply_msg(event, f"获取群成员失败：{e}"))

# ==================== 菜单注册 ====================
# 在模块顶层通过 menu_registry.register(...) 声明菜单元数据(幂等注册)

# 娱乐功能 -> 娱乐互动
_FUN_MENU_ITEMS = {
    "骰子": "🎲 骰子",
    "掷骰子": "🎲 掷骰子",
    "猜数字": "🔢 猜数字",
    "猜": "🎲 猜",
    "猜谜语": "🧩 猜谜语",
    "答案": "🎲 答案",
    "今日人品": "✨ 今日人品",
    "人品": "✨ 人品",
    "运势": "🔮 运势",
    "抽签": "🎋 抽签",
    "塔罗牌": "🃏 塔罗牌",
    "抽塔罗": "🃏 抽塔罗",
    "彩虹屁": "💐 彩虹屁",
    "夸我": "💐 夸我",
    "毒鸡汤": "🍯 毒鸡汤",
    "摸头": "💆 摸头@某人",
    "摸摸头": "💆 摸摸头@某人",
    "抽耳光": "✋ 抽耳光@某人",
    "送礼物": "🎁 送礼物@某人",
    "送礼": "🎁 送礼@某人",
    "随机CP": "💑 随机CP",
    "今日CP": "💑 今日CP",
}

for _item_name, _text in _FUN_MENU_ITEMS.items():
    menu_registry.register(
        category="娱乐功能",
        item_name=_item_name,
        text=_text,
        subcategory="娱乐互动",
        category_title="🎮 娱乐功能",
        category_trigger="娱乐功能",
        category_description="娱乐互动·小游戏·群内模拟",
        subcategory_title="🎮◇━娱乐互动━◇🎮",
        subcategory_trigger="娱乐互动",
        subcategory_description="骰子·猜数字·猜谜语·人品·运势·抽签·塔罗·彩虹屁·毒鸡汤·动作·CP",
    )
