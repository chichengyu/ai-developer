# rn-news-feed

A more substantial React Native example than `examples/react-native-counter/`.
Demonstrates:

- zustand store with `useShallow` for multi-field selection.
- Initial load via `useEffect` + explicit `refresh` action.
- `FlatList` + `RefreshControl` for pull-to-refresh.
- `useFeedStore.getState().refresh()` outside React (event handler).
- `accessibilityLabel` + `accessible` for screen readers.
- Test with `@testing-library/react-native` + `useFeedStore.setState`
  for clean state between tests.

## How to run (bare)

```bash
npx @react-native-community/cli init RnNewsFeed --skip-install
cp -r examples/rn-news-feed/App.tsx RnNewsFeed/
cp -r examples/rn-news-feed/__tests__ RnNewsFeed/
cd RnNewsFeed
npm install zustand @testing-library/react-native
npm test
npx react-native run-ios
# or
npx react-native run-android
```

## How to run (Expo)

```bash
npx create-expo-app RnNewsFeed
cp -r examples/rn-news-feed/App.tsx RnNewsFeed/
cp -r examples/rn-news-feed/__tests__ RnNewsFeed/
cd RnNewsFeed
npx expo install zustand
npm install --save-dev @testing-library/react-native
npm test
```

## What to change for production

- Replace `liveFeedApi` with `axios` + interceptors.
- Add `@tanstack/react-query` for caching.
- Add `@react-navigation/native` + `@react-navigation/native-stack`
  for multi-screen.
- Add `react-native-mmkv` for storage.
- Add `react-native-reanimated` for animations.
