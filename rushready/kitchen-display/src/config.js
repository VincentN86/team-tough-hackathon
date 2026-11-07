// Static configuration: statuses, platforms, stations, menu prep times, thresholds.
// Prep times are hand-entered estimates, not learned from history.

export const MIN = 60_000;

export const STATUS = Object.freeze({
  NEW: 'new',
  IN_PROGRESS: 'in_progress',
  READY: 'ready',
  COMPLETED: 'completed',
  CANCELLED: 'cancelled',
});

export const STATUS_LABEL = {
  new: 'New',
  in_progress: 'In Progress',
  ready: 'Ready',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

// One-tap forward path, plus a "step back" path for mis-taps.
export const NEXT_STATUS = { new: 'in_progress', in_progress: 'ready', ready: 'completed' };
export const PREV_STATUS = { in_progress: 'new', ready: 'in_progress' };

// Default SLA is used only when a platform sends no promised time.
export const PLATFORMS = {
  doordash: { label: 'DoorDash', defaultSlaMin: 25 },
  ubereats: { label: 'Uber Eats', defaultSlaMin: 25 },
  grubhub: { label: 'Grubhub', defaultSlaMin: 30 },
  website: { label: 'Website', defaultSlaMin: 30 },
  phone: { label: 'Phone', defaultSlaMin: 20 },
  instore: { label: 'In-store', defaultSlaMin: 15 },
};

// capacity = how many units the station can cook at the same time.
export const STATIONS = {
  grill: { label: 'Grill', capacity: 4 },
  fryer: { label: 'Fryer', capacity: 2 },
  oven: { label: 'Pizza oven', capacity: 2 },
  saute: { label: 'Sauté', capacity: 2 },
  cold: { label: 'Cold line', capacity: 3 },
};

export const MENU = {
  'turkey-sandwich': { name: 'Turkey sandwich', station: 'cold', prepMin: 5 },
  'caesar-salad': { name: 'Caesar salad', station: 'cold', prepMin: 4 },
  'margherita-pizza': { name: 'Margherita pizza', station: 'oven', prepMin: 20 },
  'pepperoni-pizza': { name: 'Pepperoni pizza', station: 'oven', prepMin: 20 },
  'garlic-bread': { name: 'Garlic bread', station: 'oven', prepMin: 6 },
  lasagna: { name: 'Lasagna', station: 'oven', prepMin: 18 },
  burger: { name: 'Burger', station: 'grill', prepMin: 8 },
  'chicken-sandwich': { name: 'Chicken sandwich', station: 'grill', prepMin: 9 },
  salmon: { name: 'Grilled salmon', station: 'grill', prepMin: 14 },
  fries: { name: 'Fries', station: 'fryer', prepMin: 4 },
  'chicken-tenders': { name: 'Chicken tenders', station: 'fryer', prepMin: 7 },
  'spring-rolls': { name: 'Spring rolls', station: 'fryer', prepMin: 6 },
  'pad-thai': { name: 'Pad thai', station: 'saute', prepMin: 10 },
  'kids-pasta': { name: 'Kids pasta', station: 'saute', prepMin: 8 },
};

export const DEFAULT_CONFIG = Object.freeze({
  bufferMin: 2, // safety margin before promised time
  startNowMaxSlackMin: 3, // slack <= 3 -> Start Now
  startSoonMaxSlackMin: 10, // slack <= 10 -> Start Soon
  refreshSec: 20, // re-evaluate + re-sort cadence
  undoWindowSec: 3, // voice confirmation undo window
  rushThreshold: 10, // active tickets that trigger compact rush mode
  fallbackSlaMin: 20, // if the platform is unknown and no promised time
  platforms: PLATFORMS,
  stations: STATIONS,
  menu: MENU,
});

export function withConfig(overrides = {}) {
  return { ...DEFAULT_CONFIG, ...overrides };
}
