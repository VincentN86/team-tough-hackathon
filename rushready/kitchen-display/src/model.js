// Data model (JSDoc types). All timestamps are epoch milliseconds.
// Runtime code passes plain objects; these typedefs document the shape.

/**
 * @typedef {'new'|'in_progress'|'ready'|'completed'|'cancelled'} Status
 * @typedef {'doordash'|'ubereats'|'grubhub'|'website'|'phone'|'instore'} Platform
 * @typedef {'cook'|'expo'|'manager'} Role
 */

/**
 * @typedef Employee
 * @property {string} id
 * @property {string} name
 * @property {string} initials        shown on confirmed checkboxes
 * @property {Role} role              only 'manager' may override the Ready gate
 * @property {string} pin             prototype-only shift sign-in; never store plain PINs in production
 */

/**
 * @typedef Modifier
 * @property {string} id              stable id from the source platform; used to diff updates
 * @property {string} text            e.g. "no onions"
 */

/**
 * @typedef Allergy
 * @property {string} id
 * @property {string} allergen        e.g. "Sesame"
 * @property {string} [note]          e.g. "No sesame buns or sesame oil"
 * @property {'severe'|'standard'} [severity]
 * @property {string|null} itemId     null = applies to the whole order
 */

/**
 * @typedef OrderItem
 * @property {string} id
 * @property {string} menuKey         key into PrepConfig.menu
 * @property {string} name
 * @property {number} qty
 * @property {number} [prepMin]       per-unit override; otherwise from the menu
 * @property {string} [station]       override; otherwise from the menu
 * @property {Modifier[]} modifiers
 */

/**
 * @typedef OrderUpdate
 * @property {number} at
 * @property {string} source
 * @property {OrderChange[]} changes
 * @property {string[]} highlightKeys checklist keys added/changed by the update
 * @property {number|null} acknowledgedAt
 * @property {string|null} acknowledgedBy
 *
 * @typedef OrderChange
 * @property {'added'|'removed'|'changed'} kind
 * @property {'item'|'modifier'|'allergy'|'promisedAt'} target
 * @property {string} [itemId]
 * @property {string} [key]
 * @property {string} text
 * @property {string} [previousText]
 */

/**
 * @typedef Override
 * @property {string} by              manager employee id
 * @property {string} reason          typed, required
 * @property {number} at
 * @property {{key:string,text:string,type:string}[]} unconfirmed  what was skipped
 */

/**
 * @typedef Order
 * @property {string} id
 * @property {string} number          what staff say out loud ("Order 42")
 * @property {Platform} platform
 * @property {Status} status
 * @property {number} receivedAt
 * @property {number|null} promisedAt null = fall back to the platform's default SLA
 * @property {OrderItem[]} items
 * @property {Allergy[]} allergies
 * @property {string} [customer]
 * @property {number} [startedAt]
 * @property {number} [readyAt]
 * @property {number} [completedAt]
 * @property {number} [cancelledAt]
 * @property {number|null} [cancelAcknowledgedAt]
 * @property {OrderUpdate|null} updated
 * @property {Override|null} override
 * @property {number} version
 */

/**
 * A derived checklist row. Every modifier and allergy becomes one.
 * key format: "mod:<modifierId>" or "allergy:<allergyId>".
 * @typedef ChecklistItem
 * @property {string} key
 * @property {'modifier'|'allergy'} type
 * @property {string} orderId
 * @property {string|null} itemId
 * @property {string} itemName        "Whole order" for order-wide allergies
 * @property {string} text
 * @property {ModifierConfirmation|null} [confirmation]
 */

/**
 * @typedef ModifierConfirmation
 * @property {string} orderId
 * @property {string} key
 * @property {'modifier'|'allergy'} type
 * @property {string} text            snapshot of what was confirmed
 * @property {string} employeeId
 * @property {'tap'|'voice'|'typed'} method
 * @property {string|null} transcript exact words heard (voice/typed only)
 * @property {number} at
 */

/**
 * @typedef PrepConfig
 * @property {number} bufferMin
 * @property {number} startNowMaxSlackMin
 * @property {number} startSoonMaxSlackMin
 * @property {number} refreshSec
 * @property {number} undoWindowSec
 * @property {number} rushThreshold
 * @property {number} fallbackSlaMin
 * @property {Record<string,{label:string,defaultSlaMin:number}>} platforms
 * @property {Record<string,{label:string,capacity:number}>} stations
 * @property {Record<string,{name:string,station:string,prepMin:number}>} menu
 */

/**
 * Append-only. Every confirmation, undo, ignored double-confirm, status change,
 * override, update, reset, cancel and rejected voice command is recorded.
 * @typedef AuditLogEntry
 * @property {string} id
 * @property {number} at
 * @property {'order_received'|'confirm'|'confirm_ignored'|'confirm_rejected'|'undo'|'status'|'ready_blocked'|'override'|'override_rejected'|'order_updated'|'confirmation_reset'|'confirmation_removed'|'cancelled'|'acknowledged'|'voice_rejected'|'voice_cancelled'} type
 * @property {string} [orderId]
 * @property {string} [key]
 * @property {string} [text]
 * @property {string} [employeeId]
 * @property {'tap'|'voice'|'typed'} [method]
 * @property {string|null} [transcript]
 * @property {string} [detail]
 * @property {boolean} [flagged]
 */

export {};
