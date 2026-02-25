Com base no Manual da API da Cobrança do Sicredi, seguem as informações principais para as operações de criar, buscar e alterar boletos.

Para todas as operações, é obrigatório o envio dos seguintes **Headers** de autenticação:
*   **x-api-key**: Token de acesso gerado no portal do desenvolvedor.
*   **Authorization**: Bearer + Token de autenticação (access_token) obtido na operação de login.
*   **cooperativa**: Código da cooperativa do beneficiário.
*   **posto**: Código do posto/agência do beneficiário.

---

### 1. Criar Boletos (Cadastro)
A operação permite o registro de boletos individuais (Tradicional, Híbrido com QR Code ou com Distribuição de Crédito).

*   **Método:** `POST`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos`.
*   **Principais campos do Body (JSON):**
    *   `tipoCobranca`: NORMAL ou HIBRIDO.
    *   `codigoBeneficiario`: Código do convênio de cobrança.
    *   **Pagador (Objeto):** `documento`, `nome`, `endereco`, `cidade`, `uf`, `cep`.
    *   `especieDocumento`: Ex: DUPLICATA_MERCANTIL_INDICACAO.
    *   `dataVencimento`: Formato `YYYY-MM-DD`.
    *   `valor`: Valor nominal do título.
    *   `seuNumero`: Número de controle interno do beneficiário.
*   **Retorno:** Se for híbrido, retorna o `txid` e `qrCode`. Para todos, retorna a `linhaDigitavel`, `codigoBarras` e `nossoNumero`.

---

### 2. Buscar Boletos (Consulta)
Existem diferentes formas de consultar a situação dos títulos na carteira.

#### A. Consulta por Nosso Número
Busca os detalhes completos de um boleto específico.
*   **Método:** `GET`.
*   **Endpoint (v1):** `/cobranca/boleto/v1/boletos`.
*   **Parâmetros (Query):** `codigoBeneficiario` e `nossoNumero`.
*   **Informações retornadas:** Situação do boleto (EM CARTEIRA, LIQUIDADO, VENCIDO, etc.), dados do pagador, datas, valores e histórico de descontos/juros.

#### B. Consulta de Liquidados por Dia
Retorna uma lista de boletos liquidados em uma data específica.
*   **Método:** `GET`.
*   **Endpoint:** `/cobranca/boleto/v1/boletos/liquidados/dia`.
*   **Parâmetros (Query):** `dia` (DD/MM/YYYY) e `codigoBeneficiario`.

#### C. Consulta por "seuNumero" ou "idEmpresa"
Utilizada para verificar se um título já foi cadastrado e evitar duplicidade.
*   **Método:** `GET`.
*   **Endpoint:** `/cobranca/boleto/v1/boletos/cadastrados`.
*   **Parâmetros (Query):** `seuNumero` ou `idTituloEmpresa`.

---

### 3. Alterar Boletos (Comandos de Instrução)
As alterações são realizadas através de comandos específicos para cada tipo de informação que se deseja modificar.

*   **Método Geral:** `PATCH`.
*   **Principais Instruções Disponíveis:**
    *   **Baixa de Boleto:** Utilizada para cancelar um boleto (ex: quando o cliente pagou por outro meio). O body vai vazio.
        *   Endpoint: `/boletos/{nossoNumero}/baixa`.
    *   **Alteração de Vencimento:** Requer a nova `dataVencimento` no body.
        *   Endpoint: `/boletos/{nossoNumero}/data-vencimento`.
    *   **Alteração de Desconto:** Permite modificar o valor ou percentual de até três descontos.
        *   Endpoint: `/boletos/{nossoNumero}/data-desconto` (para datas) ou `/valor-desconto`.
    *   **Alteração de Juros:** Requer o campo `valorOuPercentual`.
        *   Endpoint: `/boletos/{nossoNumero}/juros`.
    *   **Alteração de "Seu Número":** Permite atualizar o número de controle interno/nota fiscal.
        *   Endpoint: `/boletos/{nossoNumero}/seu-numero`.
    *   **Abatimento:** É possível conceder ou cancelar abatimentos (descontos concedidos após a emissão).
        *   Endpoints: `/conceder-abatimento` ou `/cancelar-abatimento`.

**Observação Importante:** Para comandos de alteração, o boleto geralmente não pode estar baixado ou liquidado para que a operação seja aceita.

O processo de autenticação da API de Cobrança do Sicredi utiliza o padrão **OAuth2** com tokens no formato **JWT** (JSON Web Token). A operação responsável por gerar o acesso é um **POST "token"**, que cria uma chave criptografada denominada `access_token`.

Abaixo estão os detalhes do funcionamento divididos por etapas:

### 1. Requisitos Prévios
Para realizar a autenticação, o usuário precisa de:
*   **x-api-key**: Token de acesso gerado no Portal do Desenvolvedor Sicredi.
*   **Código de Acesso (password)**: Gerado exclusivamente pelo associado através do Internet Banking (menu Cobrança > Código de Acesso > Gerar).
*   **Username**: Composto pela junção do Código do Beneficiário e o Código da Cooperativa.

### 2. Solicitação do Token (Request)
A requisição deve ser enviada para a URL de autenticação (Sandbox ou Produção) utilizando o formato `x-www-form-urlencoded`.

*   **Headers obrigatórios**:
    *   `x-api-key`: UUID de 36 caracteres.
    *   `context`: Valor fixo "COBRANCA".
    *   `Content-Type`: "application/x-www-form-urlencoded".
*   **Body da requisição**:
    *   `grant_type`: Definido como "password" para a primeira autenticação.
    *   `username`: Beneficiário + Cooperativa.
    *   `password`: Código de acesso gerado no Internet Banking.
    *   `scope`: Valor fixo "cobranca".

### 3. Resposta do Servidor (Response)
Em caso de sucesso, a API retorna um JSON contendo:
*   **access_token**: O token que deverá ser utilizado nas próximas chamadas de serviços.
*   **refresh_token**: Utilizado para gerar um novo `access_token` sem a necessidade de reenviar o usuário e senha.
*   **expires_in**: Tempo de expiração do token em segundos (ex: 300 segundos).
*   **refresh_expires_in**: Tempo de expiração do token de atualização.

### 4. Uso do Access Token
O `access_token` obtido deve ser enviado no cabeçalho das chamadas de todas as próximas operações (como cadastro ou consulta de boletos) através do parâmetro **Authorization** com o prefixo **Bearer**. **Não deve ser realizada uma nova autenticação a cada chamada**, apenas quando o token expirar.

### 5. Ciclo de Vida e Renovação
*   **Expiração do Access Token**: Quando o campo `expires_in` chegar ao fim, o desenvolvedor deve usar o `refresh_token` para renovar o acesso. Para isso, o `grant_type` no POST deve ser alterado para "refresh_token".
*   **Expiração do Refresh Token**: Caso o `refresh_token` também expire, será necessário realizar o fluxo de autenticação normal novamente, enviando `username` e `password`.

A principal diferença entre o **boleto tradicional** e o **boleto híbrido** na API de Cobrança do Sicredi reside nos meios de pagamento disponibilizados ao pagador e nas informações técnicas geradas no registro.

Abaixo estão detalhadas as características de cada modalidade:

### 1. Boleto Tradicional (Normal)
*   **Identificação**: É identificado na API pelo domínio `NORMAL` no campo `tipoCobranca`.
*   **Meios de Pagamento**: Possui apenas a **linha digitável** e o **código de barras**.
*   **Retorno da API**: No momento do cadastro, os campos destinados ao Pix (`txid` e `qrCode`) retornam como `null`.
*   **Flexibilidade**: Permite o registro com valor 0,00 caso a espécie seja "Boleto Proposta".

### 2. Boleto Híbrido
*   **Identificação**: É identificado na API pelo domínio `HIBRIDO` no campo `tipoCobranca`.
*   **Meios de Pagamento**: Contém todos os dados do boleto tradicional (linha digitável e código de barras) acrescidos de um **QR Code dinâmico** vinculado ao Pix.
*   **Escolha do Pagador**: O pagador tem a liberdade de escolher se prefere pagar via Pix (leitura do QR Code) ou pelo método tradicional (código de barras).
*   **Retorno da API**: Retorna obrigatoriamente o `txid` (identificador da transação Pix) e o `qrCode` (string para geração da imagem de leitura).
*   **Validade**: Possui o campo exclusivo `validadeAposVencimento`, que define por quantos dias o QR Code permanecerá ativo após a data de vencimento do título.

---

### Quadro Comparativo e Restrições

| Característica | Boleto Tradicional | Boleto Híbrido |
| :--- | :--- | :--- |
| **Linha Digitável / Código de Barras** | Sim | Sim |
| **QR Code (Pix)** | Não | Sim |
| **Contratação** | Padrão do produto Cobrança | Requer adesão específica à modalidade na agência e produto Pix ativo |
| **Edição de Valor** | Permitida conforme parametrização | **Não permitida**. Se o beneficiário puder editar o valor do título, o QR Code não será gerado |

**Observação**: O recurso de **Distribuição de Crédito (Split)** pode ser utilizado em ambas as modalidades, permitindo o repasse de valores para outras contas Sicredi ou de outros bancos no momento da liquidação.

Para configurar o **Webhook** da API de Cobrança do Sicredi, o processo é dividido em duas etapas principais: o desenvolvimento de uma API receptora por parte do associado e a formalização da contratação via API do Sicredi.

Abaixo estão os requisitos e passos detalhados em markdown:

### 1. Requisitos Prévios
Antes de iniciar, o associado deve:
*   Ter o produto **Cobrança** contratado com o gerente de conta na modalidade **API (Cobrança Online)**.
*   Possuir as credenciais de autenticação (**x-api-key** e **access_token**) já utilizadas nas demais operações de boleto.

---

### 2. Etapa 1: Desenvolvimento da API de Recebimento (Associate side)
O associado deve construir um endpoint que o Sicredi chamará via requisição **POST** sempre que ocorrer um evento em seus títulos.

**Orientações Técnicas:**
*   **Protocolo:** Deve ser obrigatoriamente **HTTPS** com **TLS 1.2**.
*   **Certificado:** Não pode ser autoassinado (deve ser emitido por uma autoridade certificadora).
*   **Timeout:** A API do associado deve responder em até **10 segundos**. Caso contrário, o evento será marcado como "não entregue".
*   **Retorno esperado:** Deve retornar o código **HTTP 200** em caso de sucesso.
*   **Autenticação:** No momento, a API receptora não deve possuir autenticação (o Sicredi está implementando autenticação via certificado, mas ainda não está finalizada).

**Estrutura do JSON que sua API receberá:**
O Sicredi enviará campos como: `agencia`, `posto`, `beneficiario`, `nossoNumero`, `dataEvento`, `movimento` (ex: LIQUIDACAO_PIX), `valorLiquidacao` e `idEventoWebhook`.

---

### 3. Etapa 2: Contratação do Webhook (API Sicredi)
Após ter a sua URL pronta e pública, você deve registrá-la no Sicredi através da operação de **Contratação Webhook**.

*   **Método:** `POST`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/webhook/contrato/`.
*   **Headers:**
    *   `x-api-key`: Token gerado no portal do desenvolvedor.
    *   `Authorization`: `Bearer + access_token`.
    *   `Content-Type`: `application/json`.

**Principais campos do Body (JSON) para contratação:**
*   `cooperativa`: Código da sua cooperativa.
*   `posto`: Código da sua agência.
*   `codBeneficiario`: Seu código de convênio.
*   `eventos`: Lista contendo `["LIQUIDACAO"]` (único evento disponível inicialmente).
*   `url`: A URL da sua API receptora (deve conter o protocolo https).
*   `urlStatus`: Definir como `ATIVO`.
*   `contratoStatus`: Definir como `ATIVO`.
*   `enviarIdTituloEmpresa`: (Opcional) Flag booleana para receber o `idTituloEmpresa` no evento de liquidação.

---

### 4. Manutenção e Consulta
Após a configuração, você pode gerenciar o contrato através dos seguintes recursos:
*   **Consultar Contrato (GET):** Permite verificar a URL cadastrada e o status do contrato utilizando `cooperativa`, `posto` e `beneficiario` como parâmetros de busca.
*   **Alterar Contrato (PUT):** Permite atualizar dados como a URL de destino ou o status do contrato (ativar/inativar) utilizando o `idContrato` retornado na criação.

**Eventos Monitorados:** Atualmente, o Webhook notifica liquidações ocorridas via Pix, Canais Sicredi (Rede), Outras Instituições (COMPE) e Cartório.

Para gerar uma segunda via de um boleto em formato PDF, a API de Cobrança do Sicredi disponibiliza a operação de **Impressão de Boletos**. Esta funcionalidade permite tanto a impressão inicial quanto a reimpressão de títulos tradicionais ou híbridos que já foram emitidos.

Abaixo estão as informações necessárias para realizar essa operação:

### 1. Detalhes da Requisição
A geração do PDF é feita através de uma consulta que retorna um arquivo binário.

*   **Método:** `GET`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/pdf`.
*   **Endpoint (Sandbox):** `https://api-parceiro.sicredi.com.br/sb/cobranca/boleto/v1/boletos/pdf`.

---

### 2. Parâmetros de Entrada
Diferente do cadastro, esta operação não utiliza um corpo (body) em JSON para o envio dos dados do boleto, mas sim um parâmetro na URL (Query Parameter).

*   **linhaDigitavel (Obrigatório):** Deve-se informar o código da linha digitável do boleto com **47 dígitos**, sem formatação (apenas números).

---

### 3. Cabeçalhos (Headers) Obrigatórios
Para autenticar a chamada, é necessário enviar os seguintes campos no header:

*   **x-api-key:** Token de acesso (UUID) fornecido pelo Sicredi no portal do desenvolvedor.
*   **Authorization:** O termo `Bearer` seguido do seu **access_token** válido.

---

### 4. Retorno (Response)
*   **Sucesso (HTTP 201 Created):** A API retorna o boleto em **formato binário (octet-stream)**. Se estiver utilizando ferramentas como o Postman, você deverá clicar na opção **"Download"** para salvar o arquivo PDF resultante.
*   **Falha:** Caso a linha digitável esteja incorreta ou o boleto não seja localizado, o retorno será um JSON contendo o código e a descrição do erro (ex: Erro 400 para linha digitável fora do padrão ou 422 para boleto não localizado).

**Observação Importante:** Caso o beneficiário que esteja tentando gerar o PDF seja diferente do beneficiário dono do título, a API retornará um erro de falta de autorização (401 Unauthorized).