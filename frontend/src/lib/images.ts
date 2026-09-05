// Real photos via LoremFlickr (Creative Commons Flickr photos), no API key.
// A stable "lock" seed per dish keeps the same photo each time.
function seedFrom(id: string): number {
  let s = 0;
  for (let i = 0; i < id.length; i++) s = (s * 31 + id.charCodeAt(i)) % 100000;
  return s;
}

// Curated English tags for the most iconic dishes → better photo relevance.
const TAGS: Record<string, string> = {
  arancina: "arancini,sicilian",
  "pane-ca-meusa": "sandwich,streetfood",
  panelle: "chickpea,fritters",
  crocche: "potato,croquettes",
  stigghiola: "grilled,skewers",
  frittola: "meat,streetfood",
  "sfincione-palermitano": "sfincione,focaccia",
  "pasta-sarde": "pasta,sardines",
  "anelletti-forno": "baked,pasta",
  "sarde-beccafico": "sardines,sicilian",
  "involtini-palermitana": "meat,rolls",
  cassata: "cassata,cake",
  "frutta-martorana": "marzipan,fruit",
  "sfincia-san-giuseppe": "cream,pastry",
  "gelo-mellone": "watermelon,pudding",
  iris: "fried,pastry",
  ravazzata: "brioche,pastry",
  rollo: "hotdog,pastry",
  calzone: "calzone,fried",
  babbaluci: "snails,food",
  quarume: "soup,broth",
  "caponata-palermitana": "caponata,eggplant",
  brociolone: "meat,roll",
  muffuletta: "bread,sicilian",
  "purpu-vugghiutu": "octopus,boiled",
  "spaghetti-ricci": "spaghetti,seaurchin",
  "sfincione-bagherese": "focaccia,white",
  "cannolo-piana": "cannoli,ricotta",
  "pasta-taianu": "baked,pasta",
  "pane-monreale": "bread,rustic",
  "biscotti-s": "biscuits,anise",
  "manna-madonie": "ash,tree",
  "caciocavallo-palermitano": "caciocavallo,cheese",
  "fagiolo-badda": "beans,legumes",
  "carciofi-spinosi": "artichokes,grilled",
  froscia: "omelette,ricotta",
  "cous-cous-trapanese": "couscous,fish",
  "busiate-pesto": "pasta,pesto",
  "pizza-rianata": "pizza,oregano",
  cabucio: "focaccia,sandwich",
  "graffe-trapanesi": "doughnuts,ricotta",
  ghiotta: "fish,soup",
  "genovesi-ericine": "custard,pastry",
  mustaccioli: "spiced,biscuits",
  "gambero-rosso": "redprawns,seafood",
  "caldo-freddo": "icecream,chocolate",
  "cannolo-dattilo": "cannoli,sicilian",
  "aglio-rosso-nubia": "garlic,red",
  "pane-nero-castelvetrano": "black,bread",
  "olive-nocellara": "olives,green",
  "pane-cunzato": "bread,tomato",
  "cassatelle-ricotta": "ravioli,ricotta",
  "vastedda-belice": "cheese,pecorino",
  "capperi-pantelleria": "capers,food",
  "insalata-pantesca": "salad,tomato",
  "bacio-pantesco": "cream,dessert",
  "pesto-pantesco": "pesto,tomato",
  "vino-passito": "dessert,wine",
  "tonno-rosso": "tuna,sashimi",
  "bottarga-tonno": "bottarga,pasta",
  lattume: "fried,fish",
  "bresaola-tonno": "cured,tuna",
  "polpette-tonno": "tuna,meatballs",
  "vino-marsala": "marsala,wine",
};

export function foodImage(id: string, w = 600, h = 400): string {
  const tags = TAGS[id] ?? "sicilian";
  const seed = seedFrom(id);
  return `https://loremflickr.com/${w}/${h}/${tags},food?lock=${seed}`;
}
