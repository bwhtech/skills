---
name: frappe-integrations
description: Activate when working on Frappe custom apps that integrate 3rd party platform/services (e.g. payment gateways, e-invoice portals, LLM APIs, and more)
---

## Prep

If the user has pasted some documentation reference for the 3rd party service/API, fetch and use that before planning the integration, else do web search for latest documentation until you have enough context based on the scope of the integration.

## Bootstrap

...


## Storing Credentials

* Create a single doctype for storing credentials and configurations related to the integration, e.g. `Razorpay Settings` (use proper tab breaks).
* Also support ENV variables and site config keys for the credentials, preference order: Settings Doctype > Site Config > Environment variables, unless user states not to.

## Use the Platform

* Use `Integration Request` to log all API requests made to the 3rd party service
* Before roling your own utilities functions for datetime conversions etc. ALWAYS check `apps/frappe` for utilities or DocTypes that can help. Specially: `frappe.integrations.utils` and `frappe.utils.data` module come very handy. In general, Frappe Utilities > Python standard modules (datetime, timezone etc.)

## Webhooks

* Create a submittable `XYZ Webhook Log` doctype to store webhook logs
* The handler should be separated from logic (on_submit). Even if submission of the log document fails, don't throw.