/* Каталог витрины: только данные. Цен здесь нет и не будет — их называет продавец в ответе
   на заявку, поэтому price и oldPrice всегда null. Пути к фото задаёт pexels(): сборки картинок
   перебирает tools/build.py, он же качает их в assets/img. */

const SHOP = {
  name:'Фруктовый дворец',
  address:'Санкт-Петербург, Сытнинская ул., 12',
  phoneLabel:'+7 (900) 000-00-00',
  whatsapp:'79000000000'
};

const waUrl=text=>`https://wa.me/${SHOP.whatsapp}${text ? '?text=' + encodeURIComponent(text) : ''}`;

const FREE_DELIVERY_FROM=2500;

const COURIER_FEE=250;

const PROMOS = {
  'РЫНОК10':{label:'Промокод РЫНОК10 — минус 10%'},
  'ПРИВЕТ':{label:'Промокод ПРИВЕТ — минус 200 ₽'}
};

const KEYS = {
  theme:'fd.theme',
  cardMode:'fd.cardMode',
  cart:'fd.cart.v12',
  last:'fd.last.v12',
  favs:'fd.favs.v12',
  recent:'fd.recent.v12',
  orders:'fd.orders.v12'
};

const THEME_LABELS = {
  market:'Живой рынок',
  light:'Светлая витрина',
  fig:'Инжир и золото',
  emerald:'Изумруд и пергамент',
  night:'Ночной базар'
};

const AISLES = [
  {id:'fruits',label:'Фруктовый ряд',sub:'Сочные плоды и цитрусы'},
  {id:'vegetables',label:'Овощной ряд',sub:'Бакинские томаты и хруст'},
  {id:'nuts',label:'Ореховый ряд',sub:'Светлые ядра нового урожая'},
  {id:'dried',label:'Сухофрукты',sub:'Естественной сушки без сиропа'},
  {id:'snacks',label:'Сладости к чаю',sub:'Чурчхела, пастила и лукум'},
  {id:'spices',label:'Специи и травы',sub:'Свежий помол на развес'}
];

const MONTHS = [
  {num:1,short:'Янв'},
  {num:2,short:'Фев'},
  {num:3,short:'Мар'},
  {num:4,short:'Апр'},
  {num:5,short:'Май'},
  {num:6,short:'Июн'},
  {num:7,short:'Июл'},
  {num:8,short:'Авг'},
  {num:9,short:'Сен'},
  {num:10,short:'Окт'},
  {num:11,short:'Ноя'},
  {num:12,short:'Дек'}
];

const CURRENT_MONTH=new Date().getMonth()+1;

const pexels=(id,w=640,h=480)=>`./assets/img/${id}-${w}x${h}.jpg`;

const PRODUCTS = [
  {
    id:'apple',
    name:'Яблоки',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:8138332,
    color:'#A8342E',
    season:[8,9,10,11,12,1,2],
    tag:'Хрустящие',
    together:['pear','walnut','banana'],
    note:'Держим сладкую «Галу», сочный «Фуджи» и зелёные с кислинкой. Подскажите в комментарии, любите послаще или с хрустящей кислинкой — подберём точный сорт.'
  },
  {
    id:'pear',
    name:'Груши',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:20126521,
    color:'#7D8A2D',
    season:[8,9,10,11,12],
    tag:'Медовые',
    together:['apple','walnut','grape'],
    note:'Конференц и медовые сезонные груши. Хороши к сыру и грецкому ореху; если берёте на пару дней вперёд — выберем чуть поплотнее.'
  },
  {
    id:'banana',
    name:'Бананы',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:30638212,
    color:'#C4961A',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'Спелые',
    together:['apple','mandarin','almond'],
    note:'Ровные сладкие грозди без потемнений. К утренней каше или перекусу — можем положить спелые на сегодня или чуть зеленоватые впрок.'
  },
  {
    id:'orange',
    name:'Апельсины',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:7156077,
    color:'#D4631C',
    season:[11,12,1,2,3,4],
    tag:'На фреш',
    together:['mandarin','lemon','dates'],
    note:'Выбираем самые тяжёлые плоды — в них максимум сока и тонкая кожица. Отлично идут и на утренний фреш, и в нарезку.'
  },
  {
    id:'mandarin',
    name:'Мандарины',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:1002778,
    color:'#D95823',
    season:[11,12,1,2,3],
    tag:'С веточкой',
    together:['orange','churchkhela','walnut'],
    note:'Тонкокорые, душистые, чистятся одним движением и без лишней кислинки. Пахнут на всю кухню — настоящий хит прилавка.'
  },
  {
    id:'grape',
    name:'Виноград',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:14695445,
    color:'#643269',
    season:[8,9,10,11],
    tag:'Кишмиш',
    together:['pear','walnut','sweets'],
    note:'Упругие сладкие грозди — светлый кишмиш без косточки и ароматный тёмный. Моем прямо перед подачей, чтобы ягода хрустела.'
  },
  {
    id:'lemon',
    name:'Лимоны',
    cat:'fruits',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:1414110,
    color:'#BFA119',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'Тонкая кора',
    together:['herbs','orange','apricot'],
    note:'Ароматные тонкокорые лимоны — для чая с чабрецом, запечённой рыбы и домашних заправок. Одна долька даёт яркий запах.'
  },
  {
    id:'tomato',
    name:'Помидоры',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:38444064,
    color:'#B83526',
    season:[5,6,7,8,9,10],
    tag:'Бакинские',
    together:['cucumber','pepper','onion'],
    note:'Мясистые, сладкие, с настоящим запахом грядки. Не убирайте их в холодильник — при комнатной температуре они вдвое вкуснее в салате с красным луком.'
  },
  {
    id:'cucumber',
    name:'Огурцы',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:3568039,
    color:'#2F7041',
    season:[4,5,6,7,8,9,10],
    tag:'Пупырчатые',
    together:['tomato','pepper','herbs'],
    note:'Крепкие, пупырчатые, с тонкой кожицей и без горечи. Идеальны для хрустящего салата или просто с крупной солью.'
  },
  {
    id:'pepper',
    name:'Перец сладкий',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:38346130,
    color:'#C44222',
    season:[6,7,8,9,10],
    tag:'Толстостенный',
    together:['tomato','cucumber','spices'],
    note:'Сочный толстостенный перец — хрустит в свежем салате и становится медово-сладким, если запечь его со специями.'
  },
  {
    id:'potato',
    name:'Картофель',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:9580573,
    color:'#8F7048',
    season:[7,8,9,10,11,12,1,2,3],
    tag:'Отборный',
    together:['onion','carrot','spices'],
    note:'Крепкие ровные клубни без зелени. Скажите, будете жарить или делать пюре — подберём нужный сорт прямо из ящика.'
  },
  {
    id:'carrot',
    name:'Морковь',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:9704414,
    color:'#CF611E',
    season:[7,8,9,10,11,12,1,2],
    tag:'Сладкая',
    together:['onion','potato','spices'],
    note:'Яркая, сочная и хрустящая морковь — хороша и в плов со специями, и в наваристый суп, и просто похрустеть.'
  },
  {
    id:'onion',
    name:'Лук репчатый',
    cat:'vegetables',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:144206,
    color:'#9C662B',
    season:[8,9,10,11,12,1,2,3],
    tag:'Репка и красный',
    together:['tomato','potato','carrot'],
    note:'Плотный золотистый лук для готовки и мягкий сладкий красный — для свежих салатов с бакинскими помидорами.'
  },
  {
    id:'walnut',
    name:'Грецкий орех',
    cat:'nuts',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:19396252,
    color:'#704B2F',
    season:[9,10,11,12,1,2,3,4],
    tag:'Светлые ядра',
    together:['apricot','prune','churchkhela'],
    note:'Светлые целые половинки нового урожая без горчинки. Лучшая пара к мёду, тёплой каше и домашней выпечке.'
  },
  {
    id:'almond',
    name:'Миндаль',
    cat:'nuts',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:3997459,
    color:'#8F6032',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'Крупный',
    together:['dates','raisin','hazelnut'],
    note:'Крупный золотистый миндаль со сливочным послевкусием — сырой или слегка подсушенный, выбирайте на свой вкус.'
  },
  {
    id:'hazelnut',
    name:'Фундук',
    cat:'nuts',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:1295572,
    color:'#784C27',
    season:[9,10,11,12,1,2,3],
    tag:'Цельный',
    together:['almond','dates','sweets'],
    note:'Отборные цельные ядра фундука с насыщенным ореховым ароматом — отлично к утреннему кофе и десертам.'
  },
  {
    id:'seeds',
    name:'Семечки',
    cat:'nuts',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:543730,
    color:'#54513F',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'Тыква и подсолн.',
    together:['walnut','raisin','tomato'],
    note:'Чистые тыквенные и подсолнечные семечки без шелухи — для свежих салатов, хлеба и полезных завтраков.'
  },
  {
    id:'apricot',
    name:'Курага',
    cat:'dried',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:31717506,
    color:'#C2651B',
    season:[10,11,12,1,2,3,4],
    tag:'Сахарная',
    together:['walnut','prune','herbs'],
    note:'Мясистая узбекская курага естественной сушки, без блестящего сиропа. Обдайте тёплой водой перед чаем — станет как медовая.'
  },
  {
    id:'raisin',
    name:'Изюм',
    cat:'dried',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:35166629,
    color:'#593657',
    season:[10,11,12,1,2,3,4,5],
    tag:'Без косточки',
    together:['apricot','almond','spices'],
    note:'Чистый сладкий изюм — тёмный и золотой, без веточек и косточек. В творог, домашние булочки и настоящий плов.'
  },
  {
    id:'prune',
    name:'Чернослив',
    cat:'dried',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:9508583,
    color:'#38283A',
    season:[10,11,12,1,2,3,4],
    tag:'Мягкий',
    together:['walnut','apricot','dates'],
    note:'Крупный бархатистый чернослив без косточки с лёгкой кислинкой. Классика — положить внутрь половинку грецкого ореха.'
  },
  {
    id:'dates',
    name:'Финики',
    cat:'dried',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:4469611,
    color:'#61351E',
    season:[10,11,12,1,2,3,4,5],
    tag:'Королевские',
    together:['almond','herbs','sweets'],
    note:'Крупные карамельные финики с тающей мякотью — заменяют любые конфеты к вечернему чаю.'
  },
  {
    id:'churchkhela',
    name:'Чурчхела',
    cat:'snacks',
    unit:'шт',
    weightKg:0.15,
    price:null,
    oldPrice:null,
    photo:31665655,
    color:'#782433',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'На гранате',
    together:['mandarin','sweets','herbs'],
    note:'Мягкая свежая чурчхела на гранатовом и виноградном соке с щедрой ниткой грецкого ореха. Не убирайте в холодильник — в бумаге она останется нежной.'
  },
  {
    id:'sweets',
    name:'Восточные сладости',
    cat:'snacks',
    unit:'кг',
    weightKg:1.0,
    price:null,
    oldPrice:null,
    photo:1028714,
    color:'#9C4558',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'К чаю',
    together:['churchkhela','herbs','hazelnut'],
    note:'Натуральная фруктовая пастила, мягкий рахат-лукум с орешками и рулеты — собираем ассорти прямо с прилавка.'
  },
  {
    id:'spices',
    name:'Специи на развес',
    cat:'spices',
    unit:'100 г',
    weightKg:0.1,
    price:null,
    oldPrice:null,
    photo:678414,
    color:'#AD461F',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'Свежий помол',
    together:['carrot','onion','pepper'],
    note:'Зира, барбарис, копчёная паприка, хмели-сунели и авторские сборы для плова, мяса и запечённых овощей. Насыплем столько, сколько нужно.'
  },
  {
    id:'herbs',
    name:'Сушёные травы',
    cat:'spices',
    unit:'100 г',
    weightKg:0.1,
    price:null,
    oldPrice:null,
    photo:4198023,
    color:'#336142',
    season:[1,2,3,4,5,6,7,8,9,10,11,12],
    tag:'В чай и блюда',
    together:['lemon','apricot','churchkhela'],
    note:'Горный чабрец, ароматная мята, базилик и сборы для согревающего чая. Заваривайте щепотку с долькой лимона.'
  }
];

const DAILY_HITS = ['mandarin', 'tomato', 'walnut', 'churchkhela'];

const GUIDE_DATA = {
  fruits:[{title:'Цитрусы и яблоки',text:'Держите в прохладном ящике без плотного пакета — так кожица не отсыреет, а хруст сохранится до 2 недель.'},{title:'Груши и бананы',text:'Если взяли плотные груши, оставьте их на столе рядом с яблоками на сутки — они быстро наберут медовую мягкость.'},{title:'Виноград',text:'Мойте только ту гроздь, которую подаёте на стол: сухие ягоды в холодильнике остаются упругими вдвое дольше.'}],
  vegetables:[{title:'Бакинские помидоры',text:'Никогда не прячьте спелые томаты в холодильник — холод забирает аромат. Идеально при +16…+20 °C.'},{title:'Пупырчатые огурцы',text:'Храните в открытом крафтовом пакете в нижнем ящике холодильника, чтобы кожица оставалась звонкой.'},{title:'Картофель, лук и морковь',text:'Держите картофель и лук отдельно друг от друга в тёмном сухом месте — так они не прорастают.'}],
  dried:[{title:'Орехи без горчинки',text:'Очищенные ядра лучше хранить в стеклянной банке в прохладном шкафу — масла не окисляются.'},{title:'Курага и финики',text:'Перед чаем ополосните тёплой водой и обсушите салфеткой: натуральная сладость раскроется ярче.'},{title:'Свежая чурчхела',text:'Заверните в пергамент и держите при комнатной температуре — в холодильнике гранатовый сок твердеет.'}]
};

const GALLERY_ITEMS = [
  {photo:1002778,color:'#D95823',caption:'Свежие мандарины с зелёной веточкой'},
  {photo:38444064,color:'#B83526',caption:'Мясистые бакинские томаты'},
  {photo:19396252,color:'#704B2F',caption:'Светлый грецкий орех нового урожая'},
  {photo:31665655,color:'#782433',caption:'Мягкая чурчхела на гранатовом соке'}
];
