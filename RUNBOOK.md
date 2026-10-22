# Runbook

How to set up, run and recover the index pipeline. The design is in jtm's `SPEC.md` (sections 8, 9 and 15); the root key ceremony is in jtm's [`docs/key-ceremony.md`](https://github.com/ivankahl/jtm/blob/master/docs/key-ceremony.md).

Contents: [What runs where](#what-runs-where) · [Choosing the jtm revision](#choosing-the-jtm-revision) · [Secrets and variables](#secrets-and-variables) · [Repository settings](#repository-settings) · [Keys](#keys) · [First release](#first-release) · [Dry run in a fork](#dry-run-in-a-fork) · [Every day](#every-day) · [Rotating the index key](#rotating-the-index-key) · [When something goes wrong](#when-something-goes-wrong) · [Known limits](#known-limits)

## What runs where

**Update** (`update.yml`, daily at 03:17 UTC and by hand) builds `jtm-index` from the jtm revision in `JTM_REF`, then runs one job per plugin: `jtm-index generate --dry-run --write-confirmed`. That queries the plugin's sources, downloads every artifact, computes its SHA-256 and checks it against two sources, or one source and a vendor signature, or one source and our own download (jtm SPEC section 15). The result is `confirmed/<plugin>.json`. If any file differs from the one on the default branch, the last job pushes the branch `automation/confirmed-update` and opens (or updates) a pull request, overwriting that branch each run (do not push to it; make fixes on your own branch), whose description lists the versions added and removed, every hash, and every version whose hash *changed*. It uses no secret, only the workflow's own `GITHUB_TOKEN` (`contents: write`, `pull-requests: write`, on that one job).

**Publish** (`publish.yml`) runs after a merge that changes `confirmed/` or `keys/`, every Monday 04:41 UTC, and by hand. The `plan` job (no secrets) downloads the latest release, checks it like a client would, and asks `jtm-index generate --dry-run --use-confirmed` per plugin whether any index file would change. Only when something would (or `keys/keys.json` differs from the release's) does the `publish` job start, and that job waits for approval in the `publish` environment. It signs the merged `confirmed/` files, adds `keys.json` and its signature, runs `jtm-index verify` over the result, creates a draft release with all assets, checks that every asset arrived, publishes it as the latest release, and downloads it again through `releases/latest/download/` to verify it once more.

The Monday run exists because an index that has not changed is still issued again when less than half of its 30-day validity is left (jtm SPEC section 15, "No churn"); without it a quiet month would let every index expire. You are asked to approve that release like any other.

Why the signing job asks no upstream for anything: the pull request is the review. If the signing job looked at the upstreams again, it could sign something nobody read, because an upstream changed between the review and the release. It signs exactly the merged files.

## Choosing the jtm revision

`JTM_REF` holds the revision of the jtm repository (`ivankahl/jtm`, named in `publish.yml`; `vars.JTM_REPOSITORY` for Update) that `jtm-index` is built from: the first word of the file, a branch, tag or commit SHA. The rest of the line is a comment.

- **Publish requires a full 40-character commit SHA.** The signing job runs the binary built from that revision with the signing key in its environment, so a branch that can move must not decide what that code is. Change `JTM_REF` in a pull request, like any other change to the signing path, and review the jtm diff between the old and new SHA.
- **Update accepts anything**, and its manual run has a `jtm_ref` input for trying a branch without changing the file. It holds no secret.
- The SHA committed here is the head of jtm's `claude/t6-4-index-pipeline` branch when this pipeline was written. Until the jtm pull requests of milestone M6 are merged, that is the only revision that has `jtm-index generate`, `--use-confirmed` and `verify`. After they are merged, set `JTM_REF` to the merge commit (or a release tag's commit) on jtm's default branch. A commit that only exists on a pull request branch stays fetchable by SHA while the pull request exists; after it is gone, the build fails with a clear checkout error, which is the cue to move `JTM_REF`.
- When jtm moves to `jtm-dev/jtm`, edit `repository:` in `publish.yml` (reviewed) and set the variable `JTM_REPOSITORY` for Update.

## Secrets and variables

Create these under **Settings → Environments → publish**, not as repository secrets, so that only the approved `publish` job can read them:

| Name | Kind | What |
| --- | --- | --- |
| `JTM_INDEX_SIGNING_KEY` | environment secret | The whole contents of the index key's `minisign.key` file, including the `untrusted comment:` line. |
| `JTM_INDEX_SIGNING_KEY_PASSWORD` | environment secret | The password of that key. The index key must have one: `jtm-index generate` refuses a key made with `minisign -G -W` (no password) as damaged, a limit of the `minisign` crate. Only a key with no password at all may leave this secret out. |

Repository variables (Settings → Secrets and variables → Actions → Variables):

| Name | Default | What |
| --- | --- | --- |
| `JTM_REPOSITORY` | `ivankahl/jtm` | Where the **Update** workflow builds `jtm-index` from. Publish ignores it and names the repository in `publish.yml`, because it runs the built code with the signing key and a variable is not reviewed; moving the jtm repository is a reviewed edit of that line. |
| `JTM_ROOT_KEYS` | unset | **Rehearsals in a fork only.** Space-separated root public keys that replace the manifests' root keys when `jtm-index verify` checks a release. `scripts/verify-dir.sh` refuses to run with it set in `jtm-dev/index` or `ivankahl/jtm-index`. In the real repository it must stay unset. |

The key and the password reach exactly one step, as environment variables that `jtm-index` reads (`--secret-key-env`, `--password-env`). No command line carries either, nothing prints them, and GitHub masks them in logs. Never create or paste the key anywhere else, and never generate the production index key on a CI runner or in a chat: follow the ceremony document.

## Repository settings

Things only the owner can set. The workflows cannot work, or are not safe, until these are done.

1. **Settings → Actions → General → Workflow permissions**: *Read repository contents* as the default, and tick **Allow GitHub Actions to create and approve pull requests**. Without the tick, the Update workflow pushes its branch but cannot open the pull request, and says so.
2. **Settings → Actions → General → Actions permissions**: allow actions from this repository plus the pinned ones in use: `actions/checkout`, `actions/upload-artifact`, `actions/download-artifact` and `Swatinem/rust-cache`. Every `uses:` in the workflows is a full commit SHA with the version in a comment.
3. **Settings → Environments → New environment → `publish`**:
   - *Required reviewers*: the maintainers who may release. If there is more than one, tick *Prevent self-review*.
   - *Deployment branches and tags*: *Selected branches* → the default branch only.
   - Add the two secrets above here.
4. **Settings → Branches → protect the default branch**: require a pull request with at least one approval, require the `Check` status, and block force pushes. This is what makes "a person read the diff" true: the Publish workflow signs whatever is on the default branch.
5. **Settings → Actions → General → Fork pull request workflows**: require approval for first-time contributors. No workflow here uses `pull_request_target`, and secrets are never passed to pull requests.
6. The first time you want the daily run, open the **Actions** tab and enable workflows if GitHub asks. Scheduled workflows only run on the default branch, and are switched off in forks until enabled.

A pull request created with the workflow's own token does not start other workflows (a GitHub rule against loops). So `Check` does not run on the Update pull request by itself; close and reopen it to run it, or review without it (it only re-checks the file format).

## Keys

`keys/keys.json` lists the index keys that jtm trusts to sign indices, each scoped to plugins and expiring within 90 days. It is signed offline by the root keys, two of three, and `keys/keys.json.minisig` holds the signatures. Neither is ever produced by a workflow. Build and sign them as the ceremony document says (`jtm-index keys build`, `minisign`, `jtm-index keys verify`), and commit the pair in a pull request. `.gitattributes` marks `keys/` as `-text` so no line-ending rewrite can break the signature.

Publish then:

- refuses to run until both files exist;
- releases whenever the pair differs from the one in the latest release, so a rotation reaches clients without a change to `confirmed/`;
- runs `jtm-index verify`, which loads `keys.json` with the manifests' root keys and fails unless the key that signed the indices is listed for each plugin and has not expired. This is the check T6.3 left open (its SPEC-QUESTION 7): the generator only knows the key it was given, never `keys.json`.
- warns (`W_KEY_EXPIRES_SOON`) when the newest key for a plugin ends within 14 days. Act on that warning: an index signed by a key stops verifying when the key expires.

## First release

1. Merge the pull requests of jtm that carry `jtm-index generate`, `--use-confirmed` and `verify`, or leave `JTM_REF` on the branch commit.
2. Do the [repository settings](#repository-settings) and add the secrets.
3. Run the key ceremony. Commit `keys/keys.json` and `keys/keys.json.minisig`.
4. **Actions → Update → Run workflow.** The first run downloads every artifact of every version; the Java vendors take hours. It opens a pull request that adds `confirmed/<plugin>.json` for each plugin. All five plugins must succeed once: every release holds all of them, and Publish stops with "confirmed/<plugin>.json does not exist" otherwise.
5. Review and merge it. The merge starts Publish; approve it in the `publish` environment.
6. Check the release: five plugins, `keys.json`, and a `.minisig` for each file; `https://github.com/<owner>/<repo>/releases/latest/download/keys.json` downloads.

## Dry run in a fork

This is the check that the pipeline works end to end without touching the real keys or the real repository. It needs a copy of this repository under another account or organisation (a fork, or a new repository you push this one to), because a repository cannot be forked into the account that owns it.

1. **Copy the repository** and enable Actions on the copy.
2. Do **settings 1 and 3** above on the copy. Skip the rest.
3. **Make throwaway keys** on your machine (not the real ones; these are for the copy only):

   ```sh
   mkdir rehearsal && cd rehearsal
   for i in 1 2 3; do minisign -G -W -p root-$i.pub -s root-$i.key; done
   minisign -G -p index.pub -s index.key        # asks for a password: choose one
   ```

   The index key needs its password (no `-W`), because `jtm-index generate` refuses the passwordless keys that the `minisign` tool writes.

4. **Build `keys/keys.json`** listing `index.pub` for all five plugins with an `expires` under 90 days away, and sign it with two of the three roots, as the ceremony document's rehearsal section does (`jtm-index keys build`, or the JSON by hand; then `minisign -S` with two root keys, and the two `.minisig` files concatenated into `keys/keys.json.minisig`). Commit `keys/` to the copy's default branch.
5. **Variable** `JTM_ROOT_KEYS` on the copy: the three `root-N.pub` keys (the `RW...` lines), separated by spaces. The real manifests still carry placeholder roots, so this stands in for them when `jtm-index verify` runs.
6. **Environment `publish`** on the copy: secret `JTM_INDEX_SIGNING_KEY` = the contents of `index.key`, and `JTM_INDEX_SIGNING_KEY_PASSWORD`.
7. **Actions → Update → Run workflow.** To avoid hours of downloads, run it with `jtm_ref` set to a branch of your jtm fork whose `crates/jtm-cli/plugins/*/sources.toml` limit the versions (`version_pattern`, `include_*`), or accept the wait. **Expected: a pull request "Update confirmed index entries"** with a description of what was added.
8. **Merge it.** Publish starts (or run it by hand). The `plan` job reports "first release"; approve the `publish` job. **Expected: a release `index-<time>-seq1`** under Releases, not marked pre-release and shown as Latest, with `<plugin>-<platform>.json` and `.minisig` for every index, `keys.json` and `keys.json.minisig`, and a green "Check what clients will download" step.
9. Run **Publish** again by hand. **Expected:** `plan` says nothing differs, and the `publish` job is skipped, so nothing is asked of you.

If a step fails, the message names the file, the `E_` code and the reason. The usual causes are in [When something goes wrong](#when-something-goes-wrong).

## Every day

The Update pull request is the only thing that needs a human.

- Read **"A version listed again with a different SHA-256"** first. A vendor re-published a version. jtm clients with a lockfile for it will refuse the new index (`E_LOCK_INDEX_MISMATCH`). Do not merge until you know why.
- Entries confirmed only by `computed:sha256` come from vendors with a single source (the Java vendors other than Temurin). They are marked in the file; the description lists every confirmation source.
- *Removed* versions disappear from the index. Clients with a lockfile keep their installed copies but cannot reinstall them from a fresh cache.
- Merge, then approve the `publish` environment when GitHub asks.

Failed plugins make the Update run red. The other plugins still get their pull request, and `confirmed/` keeps the last reviewed state of the failed one.

## Rotating the index key

The ceremony document ("Rotating index keys") has the key work. The part that touches this repository:

1. Generate the new index key, add it to a new `keys.json` next to the old one (overlap), sign it with the roots, and commit the pair. Publish releases it (the pair differs), still signing with the old key.
2. Replace the two secrets in the `publish` environment with the new key and password.
3. **Run Publish by hand with `force` ticked.** The dry run has no key, so it cannot see that the unchanged files would be signed again by the new key; `force` releases anyway, and the files that carried the old signature are signed again (`resigned`).
4. After the next 14 days or so, when every client has refreshed, commit a `keys.json` without the old key.

The generator verifies the previous release with the keys in the previous release's own `keys.json`, which the `plan` job has first checked against the root keys, so the old key does not need to be given anywhere.

## When something goes wrong

| Symptom | Cause and fix |
| --- | --- |
| Update: a plugin job fails with `E_INDEX_INVALID` and a list of entries | A hash has too little evidence. Common cases: a Kotlin release published without a `.sha256` sidecar, and Spring Boot CLI, which has only a SHA-1 and needs the Apache `KEYS` file pinned in its `signing_keys` before it can be confirmed. Exclude the versions with `version_pattern` / `include_*` in the plugin's `sources.toml` in jtm, or pin the key, then move `JTM_REF`. |
| Update: `E_HASH_MISMATCH` | Two sources disagree or a download does not match what a vendor claims. Treat as an attack until explained; do not work around it. |
| Update: `E_NETWORK` or a timeout | An upstream was down. Run it again. |
| Update: the branch is pushed but no pull request appears | *Allow GitHub Actions to create and approve pull requests* is off. Tick it and run again. |
| Publish: `confirmed/<plugin>.json does not exist` | Merge an Update pull request that has all plugins. |
| Publish: `keys/keys.json does not exist` | The ceremony has not been committed. |
| Publish: `E_KEY_UNTRUSTED` from `verify` | The signing key is not listed for that plugin in `keys.json`. The secret holds a key the roots never delegated to, or the delegation names other plugins. Nothing was released. |
| Publish: `E_SIGNATURE_INVALID` from `verify`, mentioning `keys.json` | `keys.json` is not signed by enough of the manifests' root keys, or the index key's delegation has expired. Nothing was released. |
| Publish: `E_INDEX_EXPIRED` from `verify` of the *previous* release | The latest release expired before this ran. Run Publish by hand with `previous_as_of` set to a UTC time when it was still valid (for example its `generated` time), and approve. |
| Publish: `JTM_REF must be a full commit SHA` | Replace the branch or tag in `JTM_REF` with the commit SHA, in a pull request. |
| Publish: the job waits | It is waiting for approval in the `publish` environment. |
| Publish: "the draft's assets are not the release directory" | An upload failed. The draft is not visible to clients; delete the draft in the Releases page and run Publish again. |
| Publish: "Check what clients will download" fails after publishing | Something between the verified files and the CDN differs. Do not delete the release (see below); run Publish again with `force`, which publishes a new release with a higher sequence. |

**Do not delete a published release to roll it back.** Clients that already fetched it remember its `sequence`, and refuse anything lower as a rollback (jtm SPEC section 9, check 3); deleting it would make `releases/latest` point at the older, lower-sequence release, which those clients then reject. Fix forward: correct `confirmed/` or `keys/` and publish again, which gives a higher sequence. A draft that was never published can be deleted freely.

## Known limits

- **Every run downloads every artifact.** `jtm-index` confirms by hashing each artifact itself and does not reuse earlier results. The Java matrix is large; the first Update run takes hours, and later ones take as long. It runs one job per plugin, with a six-hour limit each. Reusing the hash of an artifact whose URL and size are unchanged, or a download cache, is a change to `jtm-index`, not to the workflows.
- **The live endpoints are unconfirmed.** The Adoptium, Foojay and GitHub adapters were written from the documented APIs and tested against hand-written responses (jtm PR T6.1). The first real Update run is where they are confirmed; expect to adjust `sources.toml`.
- **Spring Boot CLI is refused until its signing keys are pinned**, and Kotlin releases with no checksum sidecar are refused until excluded (see the table above). Both stop Publish from ever starting, because every release must hold all five plugins.
- **Scheduled workflows** are paused by GitHub after 60 days without repository activity. The Monday run counts as activity only if something is pushed; a quiet repository may need the workflows re-enabled by hand.
- **One writer.** Publish runs one at a time (`concurrency: publish`). A run that waits for approval holds the queue.
