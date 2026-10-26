# Claude skills in this repo

Project skills (ours):

- `ayda-product-planning`, `ayda-engineering`, `ayda-quality-security`.

Third-party design skills, vendored as-is so every cloud session gets them:

| Skill | Source | Commit | License |
|---|---|---|---|
| `impeccable` (+ `.claude/agents/impeccable-*.md`) | [pbakaus/impeccable](https://github.com/pbakaus/impeccable), `plugin/` build, v4.7.1 | `6743a347db6229848348024388033e830ae4af42` | Apache-2.0 (`impeccable/LICENSE`, `impeccable/NOTICE.md`) |
| `review-animations`, `mobile-native`, `break-ui` | [emilkowalski/skills](https://github.com/emilkowalski/skills) | `2d228630ba1446365f614a108cb8252f1feda202` | MIT (`LICENSE` in each folder) |

Notes:

- Impeccable's automatic hooks (detector on every edit, Stop pass) are NOT enabled. Run checks on demand: `/impeccable audit`, `/impeccable critique`, `/impeccable polish`.
- On first use Impeccable's launcher downloads its engine binary from GitHub releases, verified against `impeccable/scripts/engine-checksums.txt`. Per-developer config and build output are gitignored.
- The only local change: `impeccable-asset-producer.md` uses `${CLAUDE_PROJECT_DIR}/.claude` instead of `${CLAUDE_PLUGIN_ROOT}`.
- Ayda's design tokens live in `docs/design/themes.md` (Graphite, Plum); point design skills there.
- To update: copy the same folders from a newer upstream commit and bump the commit in this table.
