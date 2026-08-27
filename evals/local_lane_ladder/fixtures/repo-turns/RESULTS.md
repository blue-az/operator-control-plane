# repo-turns — 26b vs 31b

Primary metric is tool calls on **passing** cells. Wall-clock is 26b's
speed advantage; do not rank on it. Not Elo. Not a seat.

Generated from 30 trial records. Machine: desktop.

| model | task | t | pass | n_calls | failed_calls | repeat | wall s |
|---|---|---:|:---:|---:|---:|:---:|---:|
| `gemma4:26b` | `bothread-lease-ttl` | 1 | 1 | 2 | 0 | 0 | 19.6 |
| `gemma4:26b` | `bothread-lease-ttl` | 2 | 1 | 2 | 0 | 0 | 3.5 |
| `gemma4:26b` | `bothread-lease-ttl` | 3 | 1 | 2 | 0 | 0 | 3.5 |
| `gemma4:31b` | `bothread-lease-ttl` | 1 | 1 | 2 | 0 | 0 | 26.9 |
| `gemma4:31b` | `bothread-lease-ttl` | 2 | 1 | 2 | 0 | 1 | 9.4 |
| `gemma4:31b` | `bothread-lease-ttl` | 3 | 1 | 2 | 0 | 1 | 9.1 |
| `gemma4:26b` | `code-stick-github-url` | 1 | 1 | 2 | 0 | 1 | 22.3 |
| `gemma4:26b` | `code-stick-github-url` | 2 | 1 | 2 | 0 | 1 | 4.0 |
| `gemma4:26b` | `code-stick-github-url` | 3 | 1 | 2 | 0 | 1 | 3.8 |
| `gemma4:31b` | `code-stick-github-url` | 1 | 1 | 4 | 0 | 0 | 39.3 |
| `gemma4:31b` | `code-stick-github-url` | 2 | 1 | 4 | 0 | 0 | 15.2 |
| `gemma4:31b` | `code-stick-github-url` | 3 | 1 | 4 | 0 | 0 | 15.2 |
| `gemma4:26b` | `groundtruth-web-port` | 1 | 1 | 2 | 0 | 0 | 21.6 |
| `gemma4:26b` | `groundtruth-web-port` | 2 | 1 | 2 | 0 | 0 | 3.2 |
| `gemma4:26b` | `groundtruth-web-port` | 3 | 1 | 2 | 0 | 0 | 3.1 |
| `gemma4:31b` | `groundtruth-web-port` | 1 | 1 | 2 | 0 | 1 | 26.2 |
| `gemma4:31b` | `groundtruth-web-port` | 2 | 1 | 2 | 0 | 1 | 7.5 |
| `gemma4:31b` | `groundtruth-web-port` | 3 | 1 | 2 | 0 | 1 | 7.5 |
| `gemma4:26b` | `ollm-utf8-sig` | 1 | 1 | 3 | 0 | 0 | 23.9 |
| `gemma4:26b` | `ollm-utf8-sig` | 2 | 1 | 3 | 0 | 0 | 5.7 |
| `gemma4:26b` | `ollm-utf8-sig` | 3 | 1 | 3 | 0 | 0 | 5.7 |
| `gemma4:31b` | `ollm-utf8-sig` | 1 | 1 | 3 | 0 | 1 | 34.8 |
| `gemma4:31b` | `ollm-utf8-sig` | 2 | 1 | 3 | 0 | 1 | 17.9 |
| `gemma4:31b` | `ollm-utf8-sig` | 3 | 1 | 4 | 1 | 0 | 17.6 |
| `gemma4:26b` | `projectkitty-snippet-lines` | 1 | 1 | 2 | 0 | 1 | 21.3 |
| `gemma4:26b` | `projectkitty-snippet-lines` | 2 | 1 | 2 | 0 | 0 | 3.1 |
| `gemma4:26b` | `projectkitty-snippet-lines` | 3 | 1 | 2 | 0 | 0 | 3.1 |
| `gemma4:31b` | `projectkitty-snippet-lines` | 1 | 1 | 2 | 0 | 1 | 26.0 |
| `gemma4:31b` | `projectkitty-snippet-lines` | 2 | 1 | 2 | 0 | 1 | 7.3 |
| `gemma4:31b` | `projectkitty-snippet-lines` | 3 | 1 | 2 | 0 | 1 | 7.2 |

## Per cell (n trials)

| model | task | pass | mean n_calls (pass only) | mean n_calls (all) |
|---|---|---|---:|---:|
| `gemma4:26b` | `bothread-lease-ttl` | 3/3 | 2.0 | 2.0 |
| `gemma4:26b` | `code-stick-github-url` | 3/3 | 2.0 | 2.0 |
| `gemma4:26b` | `groundtruth-web-port` | 3/3 | 2.0 | 2.0 |
| `gemma4:26b` | `ollm-utf8-sig` | 3/3 | 3.0 | 3.0 |
| `gemma4:26b` | `projectkitty-snippet-lines` | 3/3 | 2.0 | 2.0 |
| `gemma4:31b` | `bothread-lease-ttl` | 3/3 | 2.0 | 2.0 |
| `gemma4:31b` | `code-stick-github-url` | 3/3 | 4.0 | 4.0 |
| `gemma4:31b` | `groundtruth-web-port` | 3/3 | 2.0 | 2.0 |
| `gemma4:31b` | `ollm-utf8-sig` | 3/3 | 3.3 | 3.3 |
| `gemma4:31b` | `projectkitty-snippet-lines` | 3/3 | 2.0 | 2.0 |
