# jtm-index

The signed version indices that [jtm](https://github.com/ivankahl/jtm) reads, and the automation that builds and publishes them. The jtm SPEC calls this repository `jtm-dev/index`; the manifests compiled into jtm point at that name (`https://github.com/jtm-dev/index/releases/latest/download/...`).

jtm installs Java, Maven, Gradle, Kotlin and the Spring Boot CLI. For each of them it needs a list of versions with the download URL, size and SHA-256 of every archive, signed so that nothing between this repository and your machine can change it. This repository produces that list.

## How it works

```
 upstreams (Adoptium, Foojay, Apache, Gradle, GitHub, Maven Central)
      |  daily, no secrets
      v
 Update workflow ---> pull request: confirmed/<plugin>.json     <- a person reads the diff
                                          |  merge
                                          v
 Publish workflow  (environment "publish": approval, signing key)
      signs exactly what was merged  --->  GitHub Release  (releases/latest)
                                                  |
                                                  v
                                       jtm clients and `jtm update`
```

| Where | What | Who writes it |
| --- | --- | --- |
| `confirmed/<plugin>.json` | Every version of the plugin with URL, size, SHA-256 and which sources agreed on it. Normalised, with nothing that varies from run to run, so a diff shows only real changes. | The Update workflow, through a pull request |
| `keys/keys.json`, `keys/keys.json.minisig` | The delegated index keys, signed offline by the root keys. | The key ceremony ([jtm `docs/key-ceremony.md`](https://github.com/ivankahl/jtm/blob/master/docs/key-ceremony.md)), through a pull request |
| `JTM_REF` | The revision of the jtm repository that `jtm-index` is built from. | A person, through a pull request |
| GitHub Releases | Every signed index file with its `.minisig`, plus `keys.json` and `keys.json.minisig`. Each release is a complete copy; the newest one is `releases/latest`. | The Publish workflow only |

The signed files themselves are never committed. The release is the published state, and the tag (`index-<UTC time>-seq<N>`) is only a label: jtm reads `releases/latest/download/<file>` and decides what is newer by the signed `sequence`.

`.github/workflows/`:

| Workflow | When | Secrets | What |
| --- | --- | --- | --- |
| `update.yml` | daily, by hand | none | Confirms every hash and opens or updates the pull request. |
| `publish.yml` | a merge that changes `confirmed/` or `keys/`, Mondays, by hand | in the `publish` environment | Checks whether anything must be released, then signs, checks like a client, and releases. |
| `build.yml` | called by the other two | none | Builds `jtm-index` from the pinned jtm revision. |
| `check.yml` | pull requests | none | Tests the helper scripts. |

Everything you need to run it is in [RUNBOOK.md](RUNBOOK.md).
