# Lion Legacy Dispatch Mobile (Expo)

Native mobile application scaffold for the dispatching/TMS platform.  
This app uses the same Supabase backend (auth, database, storage, and messaging model) as the web system.

## Tech Stack

- Expo React Native + TypeScript
- Expo Router (`src/app`)
- Supabase Auth / Database / Storage (`@supabase/supabase-js`)
- Expo Push Notifications
- EAS Build configuration for iOS + Android

## Environment Variables

Copy `.env.example` to `.env` and set:

- `EXPO_PUBLIC_SUPABASE_URL`
- `EXPO_PUBLIC_SUPABASE_ANON_KEY`
- `EXPO_PUBLIC_EAS_PROJECT_ID` (required for production push token registration)

## Role-Based Access

Login only (no public routes).  
After login, role is loaded from `profiles` and users are routed to:

- Driver tabs
- Dispatcher tabs
- Owner tabs

Owner-operator users (`is_owner_operator = true`) also receive **Driver View** workflows within the owner experience.

## Shared Feature Modules Included

- Push notification registration + token persistence (`mobile_push_tokens`)
- In-app alerts feed + realtime alert listener (`alerts`)
- Chat center (`chat_threads`, `chat_messages`)
- Load data + status events (`loads`, `load_status_events`)
- Driver location check-ins (`load_location_checkins`)
- Document upload/download scaffolding (`load-documents` storage bucket + `load_documents`)

## Dispatcher Placeholder Hooks

- Broker call/text telephony placeholder hooks for Twilio/Telnyx/Vapi
- Broker/factoring document email action placeholder via Supabase Edge Function (`send-broker-document`)

## Run

```bash
npm install
npm run start
```

## EAS Build

```bash
eas build --platform ios
eas build --platform android
```

Config is in:

- `app.config.ts`
- `app.json`
- `eas.json`

Bundle/package placeholders:

- iOS: `com.lionlegacy.dispatchmobile`
- Android: `com.lionlegacy.dispatchmobile`
