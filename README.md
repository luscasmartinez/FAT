# Painel de faturamento

Dashboard de análise do faturamento líquido, com a regra de negócio aplicada em um único cálculo e a identidade visual do Book Comercial.

## Como executar

No terminal, a partir da pasta `dashboard`:

```bash
python -m pip install -r requirements.txt
python -m faturamento.validacao
streamlit run app.py
```

As bases padrão são `Faturamento_Liquido_2026/26-11.xlsx`, `Meta_2026/meta_26-11.xlsx` e `Economias_2026/26-11_Economias_Fat.xlsx`. Cada base pode ser substituída separadamente pela barra lateral; só entra em uso depois da validação.

## Regra de faturamento

O Faturamento Líquido de Água é a soma de `CONTAS DE ÁGUA`, `CONTAS DE ÁGUA SB` e `ABATIMENTO DE ÁGUA`. O Faturamento Líquido de Esgoto é a soma de `CONTAS DE ESGOTO`, `CONTAS DE ESGOTO SB` e `ABATIMENTO DE ESGOTO`. O Faturamento de Indiretas soma os grupos `INDIRETAS ÁGUA` e `INDIRETAS ESGOTO`; o Faturamento Total Líquido soma esses três resultados. Os nomes dos abatimentos correspondem aos valores observados na coluna `CLASSE_RUBRICA` da base original. Cada linha entra uma vez e valores negativos permanecem negativos.

## Abas

- Visão geral: total e os oito componentes, composição, barras e tabela.
- Cidades: ranking, composição e tabela, com foco em um município.
- COD_GRUPO: a mesma leitura por código de grupo da ligação.
- Rubricas: ranking, pesquisa e participação por descrição.

## Comparação com a meta

O painel carrega `Meta_2026/meta_26-11.xlsx`, aba `Sheet1`, e `Economias_2026/26-11_Economias_Fat.xlsx`. A referência mais recente compartilhada entre os dois arquivos é usada; no conjunto atual, `01/11/2026`. Cabeçalhos são aparados nas extremidades (`MICRO ` na planilha de meta passa a `MICRO`); para economias, os nomes são normalizados para maiúsculas (`tipo`/`TIPO`, `Referencia`/`REFERENCIA`). As cidades são relacionadas após normalização de caixa, espaços e acentos, preservando o nome original na tela. A meta é relacionada por cidade, `COD_GRUPO`, referência e `AGRUPADOR`; chaves de meta duplicadas são sinalizadas e excluídas, sem soma automática.

As metas de faturamento usam `SERVIÇO BÁSICO` + `DIRETAS ÁGUA` para água, `DISP ESGOTO` + `DIRETAS ESGOTO` para esgoto e os dois agrupadores `INDIRETAS` para indiretas. O realizado líquido mantém os abatimentos de água e esgoto separados e negativos; como não existe agrupador de meta para abatimentos, eles são mostrados na reconciliação e não são distribuídos na meta.

Volumes faturados (`SumVOLUME_FATURADO`, em m³) e economias faturadas (`SumQTD_ECONOMIAS`, quantidade) são comparados em tabelas separadas, sem inclusão nos totais financeiros. Valores vazios são informados e a soma usa os valores numéricos disponíveis; `SumVOLUME_FATURADO_CORSAN` não substitui a coluna de volume faturado. Se não houver valor numérico disponível, o realizado fica N/A. Metas zero ou ausentes não geram diferença nem percentual. Quando um realizado não encontra meta na chave exata, o status é N/A/Sem meta e a reconciliação informa o valor sem correspondência.

## Persistência

O backend padrão é `local`. A partir da pasta `dashboard`, os arquivos ficam em `./storage/<tipo>/atual/`, versões anteriores em `historico/` e `historico/arquivadas/`, metadados em `metadata.json` e relatórios de validação JSON/CSV em `storage/relatorios/`. O `.gitignore` exclui essa pasta e arquivos temporários.

Variáveis de ambiente:

| Variável | Padrão | Uso |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` | `local` ou `s3` |
| `STORAGE_DIR` | `./storage` | Raiz local persistente |
| `MAX_VERSOES` | `5` | Total de versões não arquivadas, incluindo a atual; as mais antigas são arquivadas, nunca apagadas |
| `MAX_UPLOAD_MB` | `50` | Tamanho máximo por upload |
| `S3_ENDPOINT` | vazio | Endpoint S3-compatível |
| `S3_BUCKET` | vazio | Bucket existente |
| `S3_ACCESS_KEY` | vazio | Chave de acesso; não inclua no repositório |
| `S3_SECRET_KEY` | vazio | Segredo; não inclua no repositório |
| `S3_REGION` | vazio | Região exigida pelo serviço |
| `S3_PREFIX` | vazio | Prefixo opcional dentro do bucket |

Para persistência local em Render, crie um Disk e defina `STORAGE_DIR` para o mount path desse volume (por exemplo, `/var/data/faturamento`). No Railway, anexe um Volume ao serviço e defina `STORAGE_DIR` para o mount path configurado (por exemplo, `/data/faturamento`). O diretório deve ser gravável pelo processo do app.

Em Streamlit Community Cloud, o disco local pode ser efêmero e ser apagado em reinícios. Use `STORAGE_BACKEND=s3` com um bucket S3-compatível ou hospede a aplicação com volume persistente. Configure as credenciais por variáveis protegidas do serviço ou `st.secrets`; nunca as grave em arquivos versionados. O app exige as cinco variáveis S3 quando o backend `s3` é selecionado.

Para restaurar uma versão, abra **Histórico e ações** junto à base e use **Restaurar versão anterior**. Para remover a base ativa sem apagar versões, use **Remover base atual** e confirme na caixa de diálogo; bases ausentes deixam os indicadores dependentes indisponíveis, sem zerá-los. A retenção `MAX_VERSOES` move versões antigas para `historico/arquivadas/`.

Uploads inválidos geram um relatório em `storage/relatorios/`, mas não alteram a base ativa. Um upload idêntico atualiza o evento de reupload sem criar cópia no histórico. O dashboard revalida o hash e o conteúdo das bases persistidas antes de utilizá-las.

O dashboard não implementa autenticação. Em ambiente acessível publicamente, qualquer pessoa que consiga abrir a URL pode substituir as bases; restrinja o acesso na camada de hospedagem ou habilite autenticação antes de publicar.
