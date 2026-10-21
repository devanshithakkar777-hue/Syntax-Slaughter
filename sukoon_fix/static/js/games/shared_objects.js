/* Sukoon — culturally familiar object pool shared by the cognitive games.
   Emoji are used as universally renderable "familiar objects/images" —
   several are chosen to be recognisable to an elderly person in Assam/NER
   (tea, rice, elephant, rhino, bamboo, dhol, gamusa-style basket, paddy). */

window.SukoonGames = window.SukoonGames || {};

const SukoonObjects = [
  { code: "tea", emoji: "🍵", en: "Tea", as: "চাহ" },
  { code: "rice", emoji: "🍚", en: "Rice", as: "ভাত" },
  { code: "elephant", emoji: "🐘", en: "Elephant", as: "হাতী" },
  { code: "rhino", emoji: "🦏", en: "Rhino", as: "গঁড়" },
  { code: "bamboo", emoji: "🎋", as: "বাঁহ", en: "Bamboo" },
  { code: "drum", emoji: "🥁", en: "Dhol (drum)", as: "ঢোল" },
  { code: "basket", emoji: "🧺", en: "Basket", as: "টোপোলা" },
  { code: "flower", emoji: "🌸", en: "Flower", as: "ফুল" },
  { code: "fish", emoji: "🐟", en: "Fish", as: "মাছ" },
  { code: "boat", emoji: "🛶", en: "Boat", as: "নাও" },
  { code: "sun", emoji: "☀️", en: "Sun", as: "সূৰ্য" },
  { code: "umbrella", emoji: "☂️", en: "Umbrella", as: "ছাতা" },
  { code: "lamp", emoji: "🪔", en: "Lamp", as: "চাকী" },
  { code: "cow", emoji: "🐄", en: "Cow", as: "গৰু" },
  { code: "mango", emoji: "🥭", en: "Mango", as: "আম" },
  { code: "moon", emoji: "🌙", en: "Moon", as: "চন্দ্ৰ" },
];

function skPickObjects(n) {
  const pool = [...SukoonObjects];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, n);
}
