Esta documentação detalha o funcionamento do **Pedido de Baixa** em ambiente de produção, operação utilizada para solicitar o cancelamento ou a retirada de um título da carteira de cobrança.

### 1. Detalhes da Requisição
A instrução de baixa é realizada através de uma atualização parcial do recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/baixa`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Para autenticar e direcionar a baixa ao convênio correto, os seguintes headers são exigidos:

*   **x-api-key**: Token de acesso UUID obtido no portal do desenvolvedor.
*   **Authorization**: `Bearer + Token de Autenticação` (access_token).
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código do posto/agência do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path
*   **nossoNumero**: Deve ser informado na própria URL o número de identificação do boleto no Sicredi (9 dígitos, sem formatação).

### 4. Corpo da Requisição (Body)
Diferente de outras alterações, o corpo desta requisição deve permanecer **vazio**.
```json
{ }
```

---

### 5. Retorno da API
#### Sucesso (HTTP 202 Accepted)
A resposta indica que a instrução foi recebida e enviada para processamento interno. O JSON retornado contém:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `BAIXA`.
*   **dataMovimento** e **dataHoraRegistro**: Data e hora em que a instrução foi registrada.

#### Principais Erros
| Status HTTP | Descrição do Problema |
| :--- | :--- |
| **401 Unauthorized** | Token inválido ou divergência entre as credenciais e o beneficiário informado. |
| **422 Unprocessable Entity** | Título já baixado, já liquidado ou em fluxo de negativação/protesto. |
| **422 Unprocessable Entity** | Solicitação anterior ainda está em processamento. |
| **429 Too Many Requests** | Excesso de requisições enviadas em curto espaço de tempo. |

**Observação:** A baixa costuma ser utilizada quando o associado recebe o pagamento por outro meio e deseja invalidar o boleto para evitar pagamentos em duplicidade.

---
Esta documentação detalha o funcionamento da **Alteração de Vencimento** em ambiente de produção, operação utilizada para prorrogar ou alterar a data de vencimento de um boleto já registrado.

### 1. Detalhes da Requisição
A alteração é realizada através de uma atualização parcial do recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/data-vencimento`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Os seguintes headers são necessários para autenticar e processar a instrução:

*   **x-api-key**: Token de acesso UUID obtido no portal do desenvolvedor.
*   **Authorization**: `Bearer + Token de Autenticação` (access_token).
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código da agência/posto do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path e Body
*   **Parâmetro de Path (nossoNumero)**: Informar na URL o número de identificação do boleto no Sicredi (9 dígitos).
*   **Corpo da Requisição (Body)**:
    ```json
    {
      "dataVencimento": "YYYY-MM-DD"
    }
    ```
    *   **dataVencimento**: Nova data de vencimento desejada, no formato Ano-Mês-Dia.

---

### 4. Retorno da API
#### Sucesso (HTTP 202 Accepted)
Indica que a operação foi recebida com sucesso e enfileirada para processamento. O JSON de retorno contém:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `ALTERA_VENCIMENTO`.
*   **dataHoraRegistro**: Data e hora exata do registro da instrução.

#### Principais Erros (Cenários Negativos)
| Status HTTP | Descrição do Problema |
| :--- | :--- |
| **401 Unauthorized** | Token ausente, inválido ou divergência entre os dados do cabeçalho e as credenciais do usuário. |
| **422 Unprocessable Entity** | Título já baixado ou já liquidado. |
| **422 Unprocessable Entity** | Título aguardando confirmação de registro inicial. |
| **422 Unprocessable Entity** | Nova data de vencimento inferior à data de processamento (ou limite permitido). |

**Observação:** Por padrão, o recurso de cadastro e alteração responde em milissegundos.
---
Esta documentação detalha o funcionamento da **Alteração de Juros** em ambiente de produção, operação utilizada para modificar o valor ou o percentual de juros de mora aplicados a um título após o vencimento,.

### 1. Detalhes da Requisição
A alteração é efetuada por meio de uma atualização parcial (PATCH) no recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/juros`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Os seguintes cabeçalhos devem ser enviados para autenticar e direcionar a instrução ao beneficiário correto:

*   **x-api-key**: Token de acesso UUID gerado no portal do desenvolvedor.
*   **Authorization**: `Bearer + Token de Autenticação` (access_token) obtido no login.
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código da agência/posto do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path e Body
*   **Parâmetro de Path (nossoNumero)**: Deve-se informar na URL o número de identificação do boleto no Sicredi com 9 dígitos,.
*   **Corpo da Requisição (Body)**:
    ```json
    {
      "valorOuPercentual": "0.00"
    }
    ```
    *   **valorOuPercentual**: Novo valor (em reais) ou percentual de juros a ser cobrado por dia de atraso,.

---

### 4. Retorno da API
#### Sucesso (HTTP 202 Accepted)
Indica que a instrução foi recebida com sucesso e enfileirada para processamento interno. O JSON de retorno inclui:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `ALTERA_JUROS`.
*   **dataHoraRegistro**: Data e hora exata em que a instrução foi registrada.

#### Regras de Negócio e Falhas (Cenários Negativos)
| Status HTTP | Descrição do Problema |
| :--- | :--- |
| **401 Unauthorized** | Token ausente, expirado ou `x-api-key` inválido. |
| **422 Unprocessable Entity** | Juros maiores ou iguais ao valor total do título para a espécie DUPLICATA MERCANTIL INDICAÇÃO. |
| **422 Unprocessable Entity** | Percentual de juros informado é igual ou superior a 100%. |
| **422 Unprocessable Entity** | Título já baixado, liquidado ou aguardando confirmação de registro,. |

**Observação:** Por padrão, as operações de comando de instrução na API do Sicredi respondem em milissegundos.
---
Esta documentação detalha o funcionamento do **Comando de Instrução – Conceder Abatimento** em ambiente de produção, operação utilizada para conceder um valor de abatimento (desconto aplicado após a emissão e registro) em um boleto.

### 1. Detalhes da Requisição
A instrução é realizada através de uma atualização parcial (PATCH) no recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/conceder-abatimento`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Para autenticar a chamada e direcionar a operação ao convênio correto, devem ser enviados:

*   **x-api-key**: Token de acesso UUID fornecido pelo portal do desenvolvedor.
*   **Authorization**: `Bearer + access_token` (token obtido na autenticação).
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código do posto/agência do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path e Body
*   **Parâmetro de Path (nossoNumero):** Número de identificação do boleto no Sicredi (9 dígitos, sem formatação).
*   **Corpo da Requisição (Body):**
    ```json
    {
      "valorAbatimento": "12.34"
    }
    ```
    *   **valorAbatimento (Obrigatório):** Valor em reais a ser concedido como abatimento no título.

---

### 4. Retorno da API
#### Sucesso (HTTP 202 Accepted)
Indica que a instrução foi recebida e enfileirada para processamento interno. O JSON de retorno contém:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `PEDIDO_ABATIMENTO`.
*   **dataMovimento** e **dataHoraRegistro**: Informações temporais do registro da instrução.

#### Principais Erros (Cenários Negativos)
| Status HTTP | Mensagem/Descrição |
| :--- | :--- |
| **401 Unauthorized** | Token ausente, expirado ou `x-api-key` inválido. |
| **400 Bad Request** | Título já possui uma instrução de abatimento concedida. |
| **422 Unprocessable Entity** | Título aguardando confirmação de registro, já liquidado ou enviado para Cartório/Serasa. |
| **422 Unprocessable Entity** | Valor de abatimento informado é considerado inválido. |
| **422 Unprocessable Entity** | Uma solicitação anterior para o mesmo título ainda está em processamento. |

**Observação:** Por padrão, o recurso de comando de instrução responde em milissegundos. Se o título não for encontrado através do Nosso Número informado, a API retornará o erro correspondente.
---
Esta documentação detalha o funcionamento do **Comando de Instrução – Incluir Negativação** em ambiente de produção, operação utilizada para solicitar a negativação de um boleto que já se encontra vencido.

### 1. Detalhes da Requisição
A inclusão do pedido de negativação é realizada por meio de uma atualização parcial (PATCH) do recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/negativacao`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Para autenticar a operação e direcioná-la corretamente, os seguintes headers devem ser enviados:

*   **x-api-key**: Token de acesso UUID gerado no portal do desenvolvedor.
*   **Authorization**: `Bearer + access_token` válido.
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código da agência/posto do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path e Body
*   **Parâmetro de Path (nossoNumero):** Informar na URL o número de identificação do boleto no Sicredi (9 dígitos, sem formatação).
*   **Corpo da Requisição (Body):** Diferente de outras alterações, o corpo desta requisição deve ser enviado **vazio**.
    ```json
    { }
    ```

---

### 4. Retorno da API
#### Sucesso (HTTP 202 Accepted)
Indica que o comando foi recebido e enfileirado para processamento interno. O JSON de retorno contém:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `PEDIDO_NEGATIVACAO`.
*   **dataHoraRegistro**: Data e hora exata em que o comando foi registrado.

#### Regras de Negócio e Erros (Cenários Negativos)
A operação pode ser rejeitada nos seguintes casos:

| Status HTTP | Mensagem de Erro / Descrição |
| :--- | :--- |
| **401 Unauthorized** | Token ausente, expirado ou código de beneficiário divergente do usuário autenticado. |
| **422 Unprocessable Entity** | **Título ainda não venceu**: A negativação só é permitida para títulos vencidos. |
| **422 Unprocessable Entity** | **Título já liquidado ou baixado**: Não é possível negativar títulos fora da carteira ativa. |
| **422 Unprocessable Entity** | **Operação não permitida para carteira Descontada**: Títulos vinculados a operações de crédito não permitem este comando. |
| **422 Unprocessable Entity** | **Título aguardando confirmação**: O registro inicial do boleto ainda não foi processado. |
| **429 Too Many Requests** | Excesso de requisições enviadas em um curto espaço de tempo. |

**Observação:** Por padrão, a API responde às solicitações de comando de instrução em milissegundos. Se o título não for localizado pelo Nosso Número informado, a API retornará o erro correspondente.
---
Esta documentação detalha o funcionamento do **Comando de Instrução – Excluir de Negativação e Baixar Título** em ambiente de produção, operação utilizada para cancelar um pedido de negativação prévio e, simultaneamente, realizar a baixa de um boleto vencido.

### 1. Detalhes da Requisição
A instrução é processada através de uma atualização parcial do recurso do boleto.

*   **Método:** `PATCH`.
*   **Endpoint (Produção):** `https://api-parceiro.sicredi.com.br/cobranca/boleto/v1/boletos/{nossoNumero}/sustar-negativacao-baixar-titulo`.
*   **Codificação:** Unicode UTF-8.

---

### 2. Cabeçalhos (Headers) Obrigatórios
Para autenticar e direcionar a operação ao beneficiário correto, envie os seguintes headers:

*   **x-api-key**: Token de acesso UUID obtido no portal do desenvolvedor.
*   **Authorization**: `Bearer + access_token` (token obtido na autenticação).
*   **Content-Type**: `application/json`.
*   **cooperativa**: Código da cooperativa do beneficiário (4 dígitos).
*   **posto**: Código da agência/posto do beneficiário (2 dígitos).
*   **codigoBeneficiario**: Código do convênio de cobrança (5 dígitos).

---

### 3. Parâmetros de Path e Body
*   **Parâmetro de Path (nossoNumero):** Identificador do boleto no Sicredi (9 dígitos, sem formatação).
*   **Corpo da Requisição (Body):** O corpo deve ser enviado **vazio**.
    ```json
    { }
    ```

---

### 4. Retorno da API
#### Sucesso (HTTP 202 Accepted)
Indica que a solicitação foi recebida e enfileirada para processamento interno. O JSON de retorno contém:
*   **transactionId**: Identificador único da transação.
*   **statusComando**: Retornará `MOVIMENTO_ENVIADO`.
*   **tipoMensagem**: Retornará `PEDIDO_SUSTAR_BAIXAR_NEGATIVACAO`.
*   **dataMovimento** e **dataHoraRegistro**: Informações temporais do registro da instrução.

#### Regras de Negócio e Erros (Cenários Negativos)
A operação será rejeitada nos seguintes casos principais:

| Status HTTP | Mensagem de Erro / Motivo |
| :--- | :--- |
| **401 Unauthorized** | Token ausente, expirado ou código de beneficiário divergente do usuário autenticado. |
| **422 Unprocessable Entity** | **Título sem negativação**: O boleto não possui um pedido de negativação ativo para ser excluído. |
| **422 Unprocessable Entity** | **Carteira Descontada**: Operação não permitida para títulos vinculados a operações de crédito. |
| **422 Unprocessable Entity** | **Título já liquidado ou baixado**: O título não está em situação que permita este comando. |
| **422 Unprocessable Entity** | **Título não cadastrado**: O Nosso Número informado não foi localizado na base. |

**Observação:** Por padrão, o recurso de comando de instrução da API responde em milissegundos.