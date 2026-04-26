// Fleek-aligned product categories — how resellers actually buy inventory
const PRODUCT_TYPES = [
  {
    name: "Workwear & Streetwear",
    emoji: "🧱",
    fleek_note: "Carhartt bundles — Detroit jackets, WIP, shorts, pants",
    keywords: ["Carhartt"]
  },
  {
    name: "Puffer & Fleece Jackets",
    emoji: "🧥",
    fleek_note: "North Face fleece & puffers, Patagonia Retro-X, Better Sweater",
    keywords: ["North Face", "Patagonia Retro", "Patagonia Better", "Patagonia Synchilla", "Patagonia Houdini", "Patagonia Nano Puff", "Champion"]
  },
  {
    name: "Rain & Hardshell Jackets",
    emoji: "🌧️",
    fleek_note: "Not on Fleek (specialty — source Arc'teryx elsewhere)",
    keywords: ["Arc'teryx Zeta", "Arc'teryx Beta", "Arc'teryx Alpha", "Arc'teryx Gamma"]
  },
  {
    name: "Insulated & Midlayers",
    emoji: "🧶",
    fleek_note: "Arc'teryx Atom, upcycled sweatshirts on Fleek",
    keywords: ["Arc'teryx Atom"]
  },
  {
    name: "Sneakers & Trainers",
    emoji: "👟",
    fleek_note: "Nike Air Force, Dunk, Adidas Samba, Gazelle, New Balance 550",
    keywords: ["Nike", "Adidas", "Converse", "New Balance"]
  },
  {
    name: "Activewear & Gym Wear",
    emoji: "🏋️",
    fleek_note: "Lululemon bundles, Gymshark leggings & shorts",
    keywords: ["Lululemon", "Gymshark"]
  },
  {
    name: "Polo Shirts & Button-Downs",
    emoji: "👔",
    fleek_note: "Ralph Lauren polos & shirts, Tommy Hilfiger, Lacoste, Columbia",
    keywords: ["Ralph Lauren", "Tommy Hilfiger", "Lacoste", "Columbia"]
  },
  {
    name: "Vintage Denim & Jeans",
    emoji: "👖",
    fleek_note: "Levi's 501 bundles, Y2K bootcut jeans, Miss Me on Fleek",
    keywords: ["Levi's", "Vintage Levi's"]
  },
  {
    name: "UGG & Winter Boots",
    emoji: "🥾",
    fleek_note: "UGG Tasman & boots (seasonal on Fleek)",
    keywords: ["UGG"]
  },
  {
    name: "Tracksuits & Y2K",
    emoji: "✨",
    fleek_note: "Juicy Couture tracksuits, Y2K tops & camis",
    keywords: ["Juicy Couture"]
  },
  {
    name: "Hiking & Trekking Boots",
    emoji: "⛰️",
    fleek_note: "Not on Fleek (German specialty — source locally)",
    keywords: ["Lowa", "Meindl"]
  },
  {
    name: "Outdoor & Trekking Gear",
    emoji: "🎒",
    fleek_note: "Not on Fleek (German specialty — source locally)",
    keywords: ["Ortlieb", "Deuter", "Vaude", "Jack Wolfskin"]
  },
  {
    name: "Sandals & Summer Shoes",
    emoji: "🩴",
    fleek_note: "Not on Fleek (seasonal specialty)",
    keywords: ["Birkenstock"]
  },
  {
    name: "Designer Shoes & Flats",
    emoji: "👠",
    fleek_note: "Not on Fleek (luxury — source via consignment)",
    keywords: ["Chanel", "Miu Miu", "Repetto", "Tory Burch"]
  },
];