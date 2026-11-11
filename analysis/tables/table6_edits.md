# Edit set v2: recall on R1-accepted edits by type; SUPPORTED retention on originals

| system | condition | set | n | recall_exact | recall_error_label | recall status | n status | recall scope | n scope | recall actor | n actor | recall inference | n inference | recall dropped_condition | n dropped_condition | CON recall actor | CON n actor | CON recall amount | CON n amount | CON recall condition | CON n condition | CON recall date | CON n date | CON recall scope | CON n scope | CON recall status | CON n status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt55 | C0 | accepted MIS | 120 | 0.192 | 0.250 | 0.269 | 26 | 0.097 | 31 | 0.174 | 23 | 0.500 | 16 | 0.042 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| gpt55 | C0 | accepted CON | 30 | 0.333 | 0.367 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 0.133 | 15 | 1.000 | 2 | 0.400 | 10 | 0.000 | 1 | 1.000 | 1 |
| gpt55 | C0 | unchecked CON (secondary, LLM-generated) | 120 | 0.183 | 0.200 |  |  |  |  |  |  |  |  |  |  | 0.857 | 14 | 0.046 | 65 | 0.500 | 4 | 0.100 | 30 | 0.000 | 5 | 1.000 | 2 |
| gpt55 | C0 | originals (SUPPORTED retention) | 148 | 0.865 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| gpt55 | C1 | accepted MIS | 120 | 0.692 | 0.717 | 0.923 | 26 | 0.871 | 31 | 0.522 | 23 | 0.938 | 16 | 0.208 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| gpt55 | C1 | accepted CON | 30 | 0.900 | 0.900 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 0.867 | 15 | 1.000 | 2 | 0.900 | 10 | 1.000 | 1 | 1.000 | 1 |
| gpt55 | C1 | unchecked CON (secondary, LLM-generated) | 120 | 0.933 | 0.950 |  |  |  |  |  |  |  |  |  |  | 0.857 | 14 | 0.938 | 65 | 1.000 | 4 | 0.933 | 30 | 1.000 | 5 | 1.000 | 2 |
| gpt55 | C1 | originals (SUPPORTED retention) | 148 | 0.919 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| gpt55 | C2 | accepted MIS | 120 | 0.708 | 0.742 | 0.962 | 26 | 0.839 | 31 | 0.522 | 23 | 0.875 | 16 | 0.333 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| gpt55 | C2 | accepted CON | 30 | 1.000 | 1.000 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 1.000 | 15 | 1.000 | 2 | 1.000 | 10 | 1.000 | 1 | 1.000 | 1 |
| gpt55 | C2 | unchecked CON (secondary, LLM-generated) | 120 | 0.992 | 1.000 |  |  |  |  |  |  |  |  |  |  | 0.929 | 14 | 1.000 | 65 | 1.000 | 4 | 1.000 | 30 | 1.000 | 5 | 1.000 | 2 |
| gpt55 | C2 | originals (SUPPORTED retention) | 148 | 0.959 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C0 | accepted MIS | 120 | 0.017 | 0.017 | 0.000 | 26 | 0.000 | 31 | 0.000 | 23 | 0.125 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C0 | accepted CON | 30 | 0.033 | 0.067 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.000 | 15 | 0.500 | 2 | 0.000 | 10 | 0.000 | 1 | 0.000 | 1 |
| haiku | C0 | unchecked CON (secondary, LLM-generated) | 120 | 0.025 | 0.033 |  |  |  |  |  |  |  |  |  |  | 0.071 | 14 | 0.000 | 65 | 0.000 | 4 | 0.033 | 30 | 0.000 | 5 | 0.500 | 2 |
| haiku | C0 | originals (SUPPORTED retention) | 148 | 0.000 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C1 | accepted MIS | 120 | 0.575 | 0.608 | 0.692 | 26 | 0.774 | 31 | 0.391 | 23 | 0.875 | 16 | 0.167 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C1 | accepted CON | 30 | 0.833 | 0.867 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.867 | 15 | 0.500 | 2 | 0.900 | 10 | 1.000 | 1 | 1.000 | 1 |
| haiku | C1 | unchecked CON (secondary, LLM-generated) | 120 | 0.908 | 0.958 |  |  |  |  |  |  |  |  |  |  | 0.786 | 14 | 0.938 | 65 | 0.750 | 4 | 0.900 | 30 | 1.000 | 5 | 1.000 | 2 |
| haiku | C1 | originals (SUPPORTED retention) | 148 | 0.919 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C2 | accepted MIS | 120 | 0.608 | 0.633 | 0.731 | 26 | 0.742 | 31 | 0.435 | 23 | 0.938 | 16 | 0.250 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| haiku | C2 | accepted CON | 30 | 0.967 | 1.000 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 1.000 | 15 | 0.500 | 2 | 1.000 | 10 | 1.000 | 1 | 1.000 | 1 |
| haiku | C2 | unchecked CON (secondary, LLM-generated) | 120 | 0.967 | 1.000 |  |  |  |  |  |  |  |  |  |  | 0.857 | 14 | 1.000 | 65 | 0.750 | 4 | 0.967 | 30 | 1.000 | 5 | 1.000 | 2 |
| haiku | C2 | originals (SUPPORTED retention) | 148 | 0.959 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| nli | C0 | accepted MIS | 120 | 0.000 | 0.033 | 0.000 | 26 | 0.000 | 31 | 0.000 | 23 | 0.000 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| nli | C0 | accepted CON | 30 | 0.033 | 0.033 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.000 | 15 | 0.500 | 2 | 0.000 | 10 | 0.000 | 1 | 0.000 | 1 |
| nli | C0 | unchecked CON (secondary, LLM-generated) | 120 | 0.050 | 0.050 |  |  |  |  |  |  |  |  |  |  | 0.214 | 14 | 0.015 | 65 | 0.250 | 4 | 0.033 | 30 | 0.000 | 5 | 0.000 | 2 |
| nli | C1 | accepted MIS | 120 | 0.000 | 0.183 | 0.000 | 26 | 0.000 | 31 | 0.000 | 23 | 0.000 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| nli | C1 | accepted CON | 30 | 0.800 | 0.800 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.867 | 15 | 1.000 | 2 | 0.700 | 10 | 1.000 | 1 | 1.000 | 1 |
| nli | C1 | unchecked CON (secondary, LLM-generated) | 120 | 0.833 | 0.833 |  |  |  |  |  |  |  |  |  |  | 0.643 | 14 | 0.892 | 65 | 1.000 | 4 | 0.733 | 30 | 1.000 | 5 | 1.000 | 2 |
| nli | C2 | accepted MIS | 120 | 0.000 | 0.175 | 0.000 | 26 | 0.000 | 31 | 0.000 | 23 | 0.000 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| nli | C2 | accepted CON | 30 | 0.867 | 0.867 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 0.933 | 15 | 1.000 | 2 | 0.700 | 10 | 1.000 | 1 | 1.000 | 1 |
| nli | C2 | unchecked CON (secondary, LLM-generated) | 120 | 0.842 | 0.842 |  |  |  |  |  |  |  |  |  |  | 0.643 | 14 | 0.892 | 65 | 1.000 | 4 | 0.767 | 30 | 1.000 | 5 | 1.000 | 2 |
| qwen | C0 | accepted MIS | 120 | 0.000 | 0.000 | 0.000 | 26 | 0.000 | 31 | 0.000 | 23 | 0.000 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| qwen | C0 | accepted CON | 30 | 0.000 | 0.000 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.000 | 15 | 0.000 | 2 | 0.000 | 10 | 0.000 | 1 | 0.000 | 1 |
| qwen | C0 | unchecked CON (secondary, LLM-generated) | 120 | 0.000 | 0.000 |  |  |  |  |  |  |  |  |  |  | 0.000 | 14 | 0.000 | 65 | 0.000 | 4 | 0.000 | 30 | 0.000 | 5 | 0.000 | 2 |
| qwen | C0 | originals (SUPPORTED retention) | 148 | 0.338 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| qwen | C1 | accepted MIS | 120 | 0.142 | 0.150 | 0.192 | 26 | 0.129 | 31 | 0.087 | 23 | 0.312 | 16 | 0.042 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| qwen | C1 | accepted CON | 30 | 0.233 | 0.667 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.267 | 15 | 0.500 | 2 | 0.100 | 10 | 0.000 | 1 | 1.000 | 1 |
| qwen | C1 | unchecked CON (secondary, LLM-generated) | 120 | 0.383 | 0.692 |  |  |  |  |  |  |  |  |  |  | 0.214 | 14 | 0.400 | 65 | 0.500 | 4 | 0.467 | 30 | 0.200 | 5 | 0.000 | 2 |
| qwen | C1 | originals (SUPPORTED retention) | 148 | 0.926 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| qwen | C2 | accepted MIS | 120 | 0.133 | 0.142 | 0.154 | 26 | 0.161 | 31 | 0.043 | 23 | 0.312 | 16 | 0.042 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| qwen | C2 | accepted CON | 30 | 0.233 | 0.667 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.267 | 15 | 0.500 | 2 | 0.100 | 10 | 0.000 | 1 | 1.000 | 1 |
| qwen | C2 | unchecked CON (secondary, LLM-generated) | 120 | 0.342 | 0.667 |  |  |  |  |  |  |  |  |  |  | 0.143 | 14 | 0.400 | 65 | 0.500 | 4 | 0.367 | 30 | 0.000 | 5 | 0.000 | 2 |
| qwen | C2 | originals (SUPPORTED retention) | 148 | 0.966 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C0 | accepted MIS | 120 | 0.075 | 0.075 | 0.154 | 26 | 0.000 | 31 | 0.000 | 23 | 0.312 | 16 | 0.000 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C0 | accepted CON | 30 | 0.100 | 0.100 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.000 | 15 | 1.000 | 2 | 0.100 | 10 | 0.000 | 1 | 0.000 | 1 |
| sonnet | C0 | unchecked CON (secondary, LLM-generated) | 120 | 0.075 | 0.083 |  |  |  |  |  |  |  |  |  |  | 0.143 | 14 | 0.015 | 65 | 0.500 | 4 | 0.067 | 30 | 0.000 | 5 | 1.000 | 2 |
| sonnet | C0 | originals (SUPPORTED retention) | 148 | 0.020 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C1 | accepted MIS | 120 | 0.583 | 0.600 | 0.769 | 26 | 0.742 | 31 | 0.348 | 23 | 0.875 | 16 | 0.208 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C1 | accepted CON | 30 | 0.867 | 0.867 |  |  |  |  |  |  |  |  |  |  | 0.000 | 1 | 0.867 | 15 | 1.000 | 2 | 0.900 | 10 | 1.000 | 1 | 1.000 | 1 |
| sonnet | C1 | unchecked CON (secondary, LLM-generated) | 120 | 0.942 | 0.950 |  |  |  |  |  |  |  |  |  |  | 0.929 | 14 | 0.938 | 65 | 1.000 | 4 | 0.933 | 30 | 1.000 | 5 | 1.000 | 2 |
| sonnet | C1 | originals (SUPPORTED retention) | 148 | 0.932 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C2 | accepted MIS | 120 | 0.608 | 0.633 | 0.808 | 26 | 0.742 | 31 | 0.391 | 23 | 0.812 | 16 | 0.292 | 24 |  |  |  |  |  |  |  |  |  |  |  |  |
| sonnet | C2 | accepted CON | 30 | 1.000 | 1.000 |  |  |  |  |  |  |  |  |  |  | 1.000 | 1 | 1.000 | 15 | 1.000 | 2 | 1.000 | 10 | 1.000 | 1 | 1.000 | 1 |
| sonnet | C2 | unchecked CON (secondary, LLM-generated) | 120 | 1.000 | 1.000 |  |  |  |  |  |  |  |  |  |  | 1.000 | 14 | 1.000 | 65 | 1.000 | 4 | 1.000 | 30 | 1.000 | 5 | 1.000 | 2 |
| sonnet | C2 | originals (SUPPORTED retention) | 148 | 0.993 |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

Accepted = R1 verdict equals the intended label and base claim confirmed SUPPORTED (D17 addendum d1). Unchecked contradiction edits are a secondary, LLM-generated set (D17 d). recall_exact: exact label; recall_error_label: CON or MIS.
