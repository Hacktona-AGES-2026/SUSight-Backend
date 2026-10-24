# Paciente de demonstração

| | |
|---|---|
| Nome (do dataset) | Pedro Freitas Medeiros, 61 anos, Porto Alegre/RS |
| Paciente / solicitação | `PAC-00152` / `SOL-2023-00002` |
| Procedimento / CID | Herniorrafia inguinal (porte médio) / K40.9 |
| Posição na fila oficial | 794 de 925 |
| Login no app | CPF `529.982.247-25`, código `123456` |
| Login no web | `medico-demo` / `demo1234` |

No dataset ele tem dor 0, limitação leve e sem piora. O laudo
[`laudo-pedro-freitas-medeiros.pdf`](laudo-pedro-freitas-medeiros.pdf) (fonte: `.html`) é **fictício** e descreve
piora: dor 8/10, limitação grave, dois encarceramentos, deterioração moderada, porte médio, ASA 3, CID K40.9,
HAS e DM2. É o arquivo para enviar pelo app e ver o OCR, o tribunal e a subida na fila.

Banco: `tools/import_dataset_queue.py` cria a conta e o histórico/contato só desse paciente (histórico vem dos
eventos do dataset; o contato é fictício). Qualquer outra conta nasce vazia.
