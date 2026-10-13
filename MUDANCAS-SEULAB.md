# Mudanças da adaptação SeuLab

Base: [browser-use/video-use](https://github.com/browser-use/video-use), commit `43cfc566833548093455c9d4a46bd69913b7e552` (8 out. 2026), licença MIT. O aviso de copyright original está em `LICENSE` e deve ser mantido.

| Arquivo | O que mudou |
|---|---|
| `helpers/transcribe.py` | Troca a ElevenLabs Scribe pelo Whisper local (faster-whisper, modelo padrão `large-v3-turbo`). Grava o resultado no mesmo formato JSON da Scribe, então o resto das ferramentas funciona sem mudança. Usa um prompt cheio de "é", "hum", "tipo" para o Whisper manter as hesitações que o editor precisa cortar. |
| `helpers/transcribe_batch.py` | Um vídeo por vez por padrão (o modelo é compartilhado) e opção `--model`. |
| `SKILL.md` | Seção "SeuLab adaptation": conversar em português simples, vertical 1080×1920 por padrão, Whisper local, sem chave de API. Ajustes nas regras que citavam a Scribe. |
| `install.md` | Reescrito para Whisper local, ambiente virtual Python, pasta `~/SeuLab` e quem não programa. |
| `pyproject.toml` | Adiciona `faster-whisper`. |
| `.env.example` | Removido (não precisa mais de chave). |

## Limites conhecidos do Whisper local

- Não separa quem está falando (todas as palavras ficam como `speaker_0`).
- Não marca risadas e aplausos.
- Às vezes ainda apaga um "é" ou "hum". O editor confere as pausas suspeitas pela forma de onda.
- No computador sem placa de vídeo, a primeira transcrição é lenta.

## Teste feito

Transcrição simulada → `pack_transcripts.py` → `render.py --build-subtitles` num vídeo vertical de teste: o "Éé" foi cortado, as legendas saíram em português com acento, no tempo certo, e o vídeo final ficou em 1080×1920. O download do modelo do Whisper não pôde ser testado no ambiente de desenvolvimento (rede bloqueada); precisa de um teste num computador real.
