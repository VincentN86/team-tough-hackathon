# RushReady Kitchen Display: Smart Food Prioritizer + Digital Kitchen Tickets

A browser prototype of a kitchen display. Tickets are ranked by **how urgently each order needs to start**, not by when it arrived. Every modifier and allergy must be **confirmed by a named person** (by tap or by voice) before the order can be marked Ready.

No backend, no build step, and no dependencies. It is plain ES modules plus Node's built-in test runner.

```bash
cd kitchen-display
npm test                      # 48 unit tests (Node 20+)
python3 -m http.server 8080   # then open http://localhost:8080
```

Use Chrome, Edge or Safari for voice. `localhost` counts as a secure context, so the microphone is allowed. Every other browser still works through the typed-command box, which runs the same parser. Open **Demo tools** for one-click scenarios and sample commands. Demo PINs appear on the sign-in screen (Maria 1111, Dev 2222, Sam 3333, manager Jordan 9999).

---

## 1. Design summary

### Assumptions
- **Prep times are configured, not learned.** They are per-menu-item estimates in `src/config.js`.
- **Station capacity** is a fixed number of parallel slots (for example, the pizza oven fits 2). Capacity is modelled **within one order only**. Load across orders on the same station is a future improvement.
- **Promised time** comes from the platform. If it's missing, the platform's default SLA is used (DoorDash/Uber Eats 25 min, Grubhub/Website 30, Phone 20, In-store 15), and the ticket says so.
- Platforms send **stable ids** for items, modifiers and allergies. Updates are diffed by id.
- State lives in memory, one kitchen per browser tab. The "two employees at once" case is handled by first-write-wins in the store. A real multi-screen deployment would need the same rule enforced server-side.
- PINs are a prototype stand-in for badge or SSO sign-in. They are shown on screen for the demo.

### How urgency is calculated (`src/urgency.js`)
```
order prep   = longest station schedule
               (units on one station are packed onto its capacity slots, longest first)
latest start = promised time − order prep − buffer (2 min, configurable)
slack        = latest start − now
Late: slack < 0 or past due · Start Now: ≤ 3 · Start Soon: ≤ 10 · On Track: > 10
```
- New tickets are sorted by slack ascending. Ties go to the earlier arrival.
- **In Progress tickets are pinned** in their own lane in the order they were started, so they never shuffle away from the cook. Their label is based on the projected finish time against the promised time.
- The board re-evaluates every **20 s**, and also immediately after any action. Moves are animated with FLIP transitions. A ticket that becomes more urgent pulses once.
- **Explainability:** every ticket shows a one-line reason, such as *"Margherita pizza takes 20 min (+2 min buffer); due in 24 min. Start within 2 min."* Expanding a ticket shows the full arithmetic and the per-station breakdown.
- **Staggering:** each station's schedule is right-aligned to the order's finish time. The result is hints like *"start Garlic bread at +34 min, Caesar salad at +36 min so everything finishes together"*.

Worked example (a unit test, and orders #45/#46 in the sample data): sandwich A arrives at 6:00 and is due at 6:30, so its latest start is 6:23. Pizza B arrives at 6:05 and is due at 6:30, so its latest start is 6:08. **B ranks above A.**

### How confirmation works (`src/kitchen.js`, `src/voice.js`)
- Every modifier and allergy becomes a checklist row tied to its item. Allergies come first and are never collapsed, in any status or in rush mode. Allergy rows use a striped magenta style, an icon and the word "ALLERGY", so they never rely on colour alone.
- The wording is always **"Confirmed by &lt;name&gt;"**. The app never says "verified".
- **Tap:** a modifier is confirmed immediately. Tapping it again undoes it, and the undo is logged. An allergy opens a step-2 dialog that needs an explicit "Confirm allergy handled".
- **Voice:** hold the button (or the Space bar) and say *"Order 42, no onions satisfied"*. A live transcript is shown on screen.
  - A modifier match shows *"Order 42 – no onions (Burger) – satisfied ✓"* with a **3-second undo**, then commits.
  - An allergy match opens the step-2 dialog with a spoken read-back. Say "confirm" or tap to finish.
  - *"Order 42, all modifiers satisfied"* confirms modifiers only. **Allergies are never bulk-confirmed.**
  - Ambiguous matches (two "no onions") ask *"Order 42 has two 'no onions'. Which item?"* and offer buttons. Saying the item name also resolves it ("Order 42, chicken sandwich no onions satisfied").
  - An unknown order or modifier, or an order that is Ready, Completed or Cancelled, shows an error, optionally speaks it, logs it, and **changes nothing**.
  - Fuzzy matching tolerates plurals, filler words and one-letter mishears. Qualifiers must agree, though: "extra sauce" never matches "no sauce" or "sauce on side".
- **Gating:** "Mark Ready" is visibly locked with the reason ("2 allergies + 4 modifiers unconfirmed"). The only bypass is a **manager override**, which needs a manager PIN and a typed reason. The override is logged, flagged on the ticket, and records exactly which items were skipped.
- **Updates:** changed or removed rows lose their confirmation, while unchanged rows keep it. A quantity change on an item resets every row on that item. The ticket shows an **UPDATED** banner listing the changes, and affected rows are tagged CHANGED until someone taps "Seen". A Ready order that gains unconfirmed rows goes back to In Progress.
- **Audit log:** confirmations record employee, time, method (`tap`/`voice`/`typed`) and the exact transcript. The log also records undos, ignored duplicate confirmations, blocked Ready attempts, overrides, updates, resets, cancellations, acknowledgements and rejected voice commands.

## 2. Data model
JSDoc types are in `src/model.js`: `Employee`, `Order`, `OrderItem`, `Modifier`, `Allergy`, `Status`, `PrepConfig`, `ChecklistItem`, `ModifierConfirmation`, `OrderUpdate`/`OrderChange`, `Override` and `AuditLogEntry`. Menu, station capacity, SLA and threshold values are in `src/config.js`.

## 3. Files
| File | What |
|---|---|
| `src/urgency.js` | `planOrderPrep`, `evaluateOrder`, `classifySlack`, `prioritize`. Pure and testable. |
| `src/voice.js` | `parseVoiceCommand` (syntax) → `resolveVoiceCommand` (match against live orders) → single / all / ambiguous / error. Pure. |
| `src/kitchen.js` | Store: confirmations, gating, override, `diffOrder`/`updateOrder`, cancel, audit log |
| `src/checklist.js` | Builds checklist rows from an order (allergies first) |
| `src/speech.js` | Mockable Web Speech wrapper (push-to-talk) and a fake recognizer for tests |
| `src/sampleData.js` | 10 fictional orders covering the edge cases, plus demo scenarios |
| `src/app.js`, `index.html`, `styles.css` | The display |
| `tests/*.test.js` | Urgency, voice parser, gating/override/concurrency/updates, speech wrapper |

### Sample orders → edge cases
| # | Shows |
|---|---|
| 38 | Late: 4 min past the latest safe start |
| 45 / 46 | Worked example: sandwich A vs pizza B |
| 47 | 3 pizzas on a 2-slot oven (40 min), staggered salad and bread, item-level fish allergy |
| 44 | No promised time, so the DoorDash 25-min default is used |
| 42 | In progress, 6 modifiers including two "no onions", order-wide and item-level allergies |
| 43 | Updated after receipt: "extra sauce" → "sauce on side" reset, "no egg" kept, "add tofu" added |
| 41 | Cancelled after receipt; stays on the board until acknowledged |
| 39 / 37 | Ready (with a severe allergy still shown) / Completed. Voice commands for these are rejected. |

Demo tools add: advance the clock 5 min, a customer edit on #42, cancel #44, a rush of 8 orders (switches on compact rush mode), and two cooks confirming the same item.

## 4. Future improvements
- **Station load balancing:** schedule across all open orders per station (oven slots shared between tickets), suggest which cook takes which ticket, and add batching hints ("3 burgers across 2 orders").
- **Learn real prep times** from Start → Ready history per item, station, time of day and staffing, with confidence ranges shown in the reason.
- **Delivery driver ETA integration:** use courier arrival time as the real deadline so food isn't ready too early or too late.
- **Speaker recognition** to identify the employee automatically from their voice, with PIN fallback.
- **Photo confirmation** for high-risk allergy orders, so a picture is attached to the confirmation record. It stays a human confirmation; the photo is evidence only.
- Server-side store with optimistic concurrency, so the first-confirmation-wins rule holds across screens, plus durable audit storage.
- A wake word as an alternative to push-to-talk, a noise-robust on-device speech model, and per-kitchen vocabulary hints.
- Bump-bar and keyboard support, and per-station filtered views.

*Prototype only. Use fictional data. This is not a validated food-safety system.*
