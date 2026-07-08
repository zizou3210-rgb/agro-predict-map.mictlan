# App Resources

`app/` now owns its local runtime resources here:

- `cimmyt_app/resources/featurehero`
- `cimmyt_app/resources/phen_transform_dataset`

Current behavior:

- `FeatureHero` is resolved only from `cimmyt_app/resources/featurehero`
- optional app-scoped datasets or helpers can also live under `app/resources`

This keeps the app self-contained and avoids relying on the shared top-level `resources/featurehero` copy at runtime.
