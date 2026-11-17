# Vigia Power BI

Esse projeto conecta um painel do Power BI a modelos de linguagem usando o Power Apps e uma pasta compartilhada no OneDrive. Quem usa o relatório digita uma pergunta em linguagem natural dentro do próprio painel, clica em enviar e recebe a análise calculada em cima dos dados filtrados naquela tela.

## Como funciona

O fluxo funciona como uma ponte simples entre a nuvem da Microsoft e uma máquina local. Dentro do Power BI existe um visual do Power Apps que enxerga os filtros ativos do relatório. Quando o usuário escreve uma pergunta e aperta o botão de envio, um fluxo grava o arquivo `requisicao.json` dentro de uma pasta sincronizada no OneDrive. Esse arquivo leva o texto da pergunta junto com os registros filtrados da base.

Enquanto isso, o script `vigia_powerbi.py` fica rodando em segundo plano e observa a data de modificação desse arquivo. Assim que detecta uma atualização, ele lê os dados, calcula estatísticas exatas das colunas numéricas e faz a contagem de frequência das categorias. Em seguida, monta um resumo compacto com uma amostra em CSV, respeitando o limite de oitenta mil caracteres para manter a resposta rápida. Se existir um arquivo `base_completa.parquet` na mesma pasta, o script prioriza essa base local no lugar do JSON enviado pelo painel.

Com o pacote pronto, o vigia consulta a API do OpenRouter passando uma lista de modelos gratuitos configurados no código. Quando a resposta volta, o texto é gravado em `resposta.txt` na mesma pasta do OneDrive. O Power Apps lê esse arquivo de volta e mostra o resultado na tela do Power BI.

## Casos de uso

Esse formato resolve bem cenários onde gestores precisam tirar dúvidas rápidas durante uma reunião sem esperar por novos gráficos. Dá para pedir resumos executivos de vendas por região, identificar os maiores desvios em uma base de chamados ou conferir rapidamente quais categorias concentram mais ocorrências depois de aplicar vários filtros cruzados. Como o cálculo numérico e as contagens são feitos em Python antes do envio, o modelo não precisa adivinhar somas ou totais, o que reduz erros de conta.

## Como configurar e executar

Você precisa de Python instalado na máquina que vai rodar o vigia, uma conta no OpenRouter para gerar uma chave de API e uma pasta local sincronizada com o OneDrive.

Comece instalando as dependências do projeto.

```bash
pip install -r requirements.txt
```

Depois, defina duas variáveis de ambiente no seu terminal. A variável `BRIDGE_DIR` aponta para a pasta local onde o `requisicao.json` será salvo e lido. A variável `OPENROUTER_API_KEY` guarda a sua chave de acesso do OpenRouter. Se você estiver em uma rede corporativa com inspeção de certificado SSL, também pode definir `VERIFY_SSL` como `false`, embora o padrão seguro seja manter a verificação ativada.

No PowerShell do Windows, a configuração fica assim.

```powershell
$env:BRIDGE_DIR = "C:\caminho\para\sua\pasta\PonteIA"
$env:OPENROUTER_API_KEY = "sua_chave_aqui"
python vigia_powerbi.py
```

Assim que o terminal mostrar que a pasta está sendo monitorada, o script já está pronto para responder às perguntas enviadas pelo Power Apps. Basta deixar essa janela aberta enquanto o painel estiver em uso e testar a primeira pergunta direto no relatório.
