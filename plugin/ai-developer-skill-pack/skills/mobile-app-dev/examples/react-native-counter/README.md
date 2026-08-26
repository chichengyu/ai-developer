# react-native-counter

Minimal React Native counter demonstrating the `threading_react_native.tsx`
pattern with zustand for state.

## How to run

```bash
# Bare RN
npx @react-native-community/cli init Counter --skip-install
# Then drop App.tsx + App.test.tsx into the project.
cd Counter
npm install zustand
npm test
npx react-native run-ios
# or
npx react-native run-android

# Expo
npx create-expo-app Counter
# Then drop App.tsx + App.test.tsx into the project.
npx expo install zustand
npm test
```

## Required dependencies (in package.json)

```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-native": "^0.76.0",
    "zustand": "^5.0.0"
  },
  "devDependencies": {
    "@testing-library/react-native": "^12.0.0",
    "jest": "^29.0.0"
  }
}
```

## What it shows

- `create()` from zustand for state (no provider needed).
- `useShallow` to select multiple fields without re-render thrashing.
- Async action (`loadFromNetwork`) defined in the store.
- `accessibilityLabel` for VoiceOver / TalkBack.