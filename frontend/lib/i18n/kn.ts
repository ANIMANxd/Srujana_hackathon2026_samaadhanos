// Kannada is a stretch goal (spec v3.3 C8). The structure is kept so strings can
// be added later; any missing key falls back to English. Every string added
// here needs a native speaker's review before the demo.

import type { MessageKey } from "./en";

export const kn: Partial<Record<MessageKey, string>> = {};
