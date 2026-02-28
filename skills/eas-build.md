# EAS Build (Expo)

How to build React Native apps using EAS CLI via `exec_cmd`.

## Repo

- Mobile repo: `farm-management-saas-mobile` (in workspace)

## Build Profiles

Available profiles in `eas.json`: `development`, `preview`, `store-review`, `production`

## Build Commands

Always use `--non-interactive` and set a high timeout (1800s) since builds take a long time.

### Android

```
exec_cmd command="cd farm-management-saas-mobile && eas build --platform android --profile preview --non-interactive" timeout=1800
```

### iOS

```
exec_cmd command="cd farm-management-saas-mobile && eas build --platform ios --profile preview --non-interactive" timeout=1800
```

### Both Platforms

```
exec_cmd command="cd farm-management-saas-mobile && eas build --platform all --profile preview --non-interactive" timeout=1800
```

## Important

- ALWAYS use `--non-interactive` flag — there is no TTY in the bot environment.
- ALWAYS set `timeout=1800` — builds can take 10-20 minutes.
- ALWAYS `cd farm-management-saas-mobile` before running eas commands.
- If user doesn't specify a profile, default to `preview`.
- If user doesn't specify a platform, ask which one (android/ios/all).
