# PrintPin

Fixa um print na tela para ajudar, de forma rápida, a visualização de algo que você precisa, enquanto continua suas tarefas.

Tirou um print? Arraste a bolinha até a borda da tela e ele fica fixado ali, por cima de tudo, sem precisar abrir pastas ou outros programas.

> Funciona no **Windows**.

## Como funciona

1. Abra o `PrintPin.exe`. Ele fica rodando na bandeja do Windows (perto do relógio).
2. Tire um print com **Print Screen** ou **Win+Shift+S**.
3. Uma bolinha com a miniatura aparece no lado direito da tela. Arraste-a.
4. Ao arrastar, aparecem pontos ao redor da borda da tela e uma prévia de onde o print vai ficar. Solte perto do ponto que quiser.
5. O print fica fixado, com o tamanho e a proporção da imagem original.

### No print fixado

| Ação | Como |
| --- | --- |
| Fechar | Passe o mouse e clique no **×** (canto superior direito) |
| Redimensionar | Arraste a **alça** (canto inferior direito) ou use o **scroll** do mouse |
| Mover | Arraste o print para outro ponto da borda |

### Bandeja

Fechar a janela do PrintPin **não** encerra o app: ele continua na bandeja. Clique com o botão direito no ícone para abrir, remover todos os prints fixados ou sair.

## Baixar o executável

O `.exe` é gerado automaticamente pelo GitHub Actions a cada commit:

1. Abra a aba **Actions** deste repositório.
2. Clique na execução mais recente (a primeira da lista).
3. Em **Artifacts**, baixe **PrintPin** e extraia o `.zip`.

Na primeira vez, o Windows pode mostrar o aviso "O Windows protegeu seu computador", porque o app não é assinado. Clique em **Mais informações → Executar assim mesmo**.

## Gerar o executável no seu PC

Requer [Python 3.10+](https://www.python.org/downloads/) com a opção "Add Python to PATH" marcada.

Dê duplo clique no `build.bat`. O executável aparece em `dist\PrintPin.exe`.

Para apenas testar, sem gerar o `.exe`:

```
pip install pyside6
python printpin.py
```

## Trocar o ícone

O ícone da bandeja, da janela e do `.exe` vem do arquivo **`icon.ico`**.

1. Converta sua imagem (PNG/JPG) para `.ico` em um site como convertio.co ou icoconvert.com, de preferência com vários tamanhos (256, 64, 32 e 16 px).
2. Substitua o `icon.ico` do repositório pelo novo, **mantendo o mesmo nome**.
3. Gere o `.exe` de novo.

Se quiser usar outro nome de arquivo, altere `ICON_FILE` no `printpin.py` e também o nome no `build.bat` e no `.github/workflows/build.yml`.

## Ajustes no código

No começo do `printpin.py`:

| Constante | O que controla |
| --- | --- |
| `ACCENT` | Cor de destaque dos pontos e da prévia |
| `DOT_SPACING` | Espaçamento entre os pontos da borda |
| `DOT_INSET` | Distância dos pontos até a borda da tela |
| `EDGE` | Margem entre o print fixado e a borda da tela |
| `RADIUS` | Arredondamento dos cantos do print |

O tamanho inicial do print fixado é definido na função `default_size`.

## Estrutura

```
printpin.py                    código do app
icon.ico                       ícone (bandeja, janela e .exe)
build.bat                      gera o .exe no seu PC
.github/workflows/build.yml    gera o .exe automaticamente no GitHub
.gitignore
README.md
```

## Tecnologia

Python com [PySide6](https://doc.qt.io/qtforpython-6/) (Qt) e PyInstaller.
