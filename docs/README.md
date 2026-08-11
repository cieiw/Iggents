# Macro ADB

Aplicação Windows sem dependências externas para gravar toques e arrastos de
um Android conectado por ADB e reproduzir uma macro com variação pequena.

## Antes de usar

1. O ADB já vem incluído em `tools/adb/`. Se preferir, também é possível usar
   uma instalação do Android Platform Tools disponível no `PATH` do Windows.
2. No telefone, habilite **Opções do desenvolvedor > Depuração USB**.
3. Conecte por USB, aceite a chave RSA mostrada no telefone e execute:

   ```powershell
   adb devices
   ```

   O estado deve ser `device`, não `unauthorized`.

4. Abra o programa:

   ```powershell
   pythonw iggents.pyw
   ```

## Uso

Escolha um telefone na lista e atribua um apelido e um **modelo/grupo**. Os
apelidos facilitam identificar cada unidade; o modelo/grupo define qual
gravação ela usará. Para gravar, selecione somente um telefone e clique em
**Gravar**. Cada painel pode usar um modelo/grupo diferente; deixá-lo em branco
cria uma macro `sem_modelo` para uso com um celular único.

Para executar, selecione vários telefones: cada um receberá automaticamente a
macro do painel escolhida para o seu modelo/grupo. Se não existir uma macro
para algum modelo, aquele telefone é ignorado e o programa informa o motivo.

Na execução, as variações mantêm a mesma ação dentro de limites configuráveis:

- pausa: variação percentual de cada intervalo gravado;
- posição: o mesmo desvio é aplicado ao início e fim de um arrasto, para não
  mudar sua direção;
- duração do arrasto: altera a velocidade sem mudar o trajeto.

Teste uma macro curta antes de usar uma sequência longa. A escala de toque é
detectada automaticamente pelo aplicativo.

O gravador suporta um dedo por vez e também registra as teclas Android Voltar,
Início, Menu e Apps recentes quando elas forem enviadas pelo aparelho. Os
arquivos ficam em `data/macros/*.json` e podem ser copiados ou editados.

## Códigos de verificação por áudio (Whisper)

O editor de macros possui duas etapas adicionais:

- **Capturar código Whisper**: grava a saída de áudio do telefone com o scrcpy,
  converte para WAV PCM mono a 16 kHz, transcreve com Whisper e salva o código
  reconhecido em `{WHISPER_CODE}`.
- **Digitar código Whisper**: lê `{WHISPER_CODE}` do telefone atual e executa
  `adb -s SERIAL shell input text CODIGO`.

### Dependências

1. O scrcpy 4.1 já está incluído em `tools/scrcpy/`.
2. Instale o FFmpeg no `PATH` do Windows ou coloque `ffmpeg.exe` em
   `tools/ffmpeg/ffmpeg.exe`.
3. Instale o backend Whisper recomendado:

   ```powershell
   py -m pip install -r requirements-whisper.txt
   ```

   Também é possível executar `tools/install_whisper_dependencies.bat`.

O modelo padrão é `small.en`. Ao adicionar a etapa, também é possível escolher
`medium.en`. O modelo é baixado pelo backend Whisper na primeira utilização.

### Isolamento por aparelho

Cada telefone utiliza exclusivamente sua própria pasta:

```text
runtime/
  SERIAL_001/
    audio.m4a
    audio.wav
    transcript.txt
    variables.json
  SERIAL_002/
    audio.m4a
    audio.wav
    transcript.txt
    variables.json
```

Para ser compatível com nomes de pasta do Windows, seriais de ADB via rede que
contêm `:` são normalizados e recebem um pequeno sufixo de hash. As variáveis
continuam vinculadas ao serial original e nunca são compartilhadas entre as
threads dos aparelhos.
