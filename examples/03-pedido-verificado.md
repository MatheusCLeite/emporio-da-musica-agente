# Conversa: 03-pedido-verificado

**Cliente:** Cadê meu pedido 8?

**Assistente** (`gemini-3.5-flash-lite`): Para eu consultar o seu pedido, por favor me informe o seu telefone ou e-mail cadastrado na compra.

**Cliente:** Meu telefone é (67) 99999-0000

> Ferramenta: `consultar_pedido({'contato': '(67) 99999-0000', 'numero': '8'})`

**Assistente** (`gemini-3.5-flash-lite`): Não consegui localizar um pedido com esse número e esse contato. Poderia conferir se o número do pedido e o telefone estão certinhos?

**Cliente:** Ops, digitei errado. O certo é (67) 99654-7821

> Ferramenta: `consultar_pedido({'contato': '(67) 99654-7821', 'numero': '8'})`

**Assistente** (`gemini-3.5-flash-lite`): Ana, o seu pedido 8 (um Kala KA-C Concert Mogno) está com o status de enviado e o código de rastreio é BRJL5544332BR. 

Como a previsão de entrega era para 28/02/2026, ela já passou. Quer que eu encaminhe o seu caso para a nossa equipe verificar o que aconteceu com a entrega?

**Cliente:** Pode encaminhar sim, usa esse mesmo telefone para contato.

> Ferramenta: `registrar_encaminhamento({'motivo': 'Previsão de entrega vencida para o pedido 8', 'resumo': 'Cliente Ana relata que a previsão de entrega do pedido 8 (Kala KA-C Concert Mogno) venceu em 28/02/2026 e solicita verificação. Rastreio: BRJL5544332BR.', 'contato': '(67) 99654-7821'})`

**Assistente** (`gemini-3.5-flash-lite`): Prontinho, Ana! Registrei o encaminhamento sob o protocolo EM-20261103-4A86. Nossa equipe entrará em contato em até 24 horas úteis. 

Precisa de mais alguma coisa por enquanto?
