# Conversa: 03-pedido-verificado

**Cliente:** Cadê meu pedido 8?

**Assistente** (`gemini-3.5-flash-lite`): Para que eu possa consultar o status do seu pedido número 8, por favor me informe o seu telefone ou e-mail cadastrado na compra.

**Cliente:** Meu telefone é (67) 99999-0000

> Ferramenta: `consultar_pedido({'numero': '8', 'contato': '(67) 99999-0000'})`

**Assistente** (`gemini-3.5-flash-lite`): Não consegui localizar um pedido com o número 8 usando esse telefone. Pode conferir se os dados estão certinhos?

**Cliente:** Ops, digitei errado. O certo é (67) 99654-7821

> Ferramenta: `consultar_pedido({'contato': '(67) 99654-7821', 'numero': '8'})`

**Assistente** (`gemini-3.5-flash-lite`): Ana, o seu pedido 8 (um Kala KA-C Concert Mogno) está com status de enviado. 

A previsão de entrega era para 28/02/2026, que acabou vencendo. O código de rastreio é BRJL5544332BR. 

Como a data passou, você gostaria que eu encaminhasse o seu caso para a nossa equipe humana verificar o que aconteceu com a entrega?

**Cliente:** Pode encaminhar sim, usa esse mesmo telefone para contato.

> Ferramenta: `registrar_encaminhamento({'resumo': 'Cliente Ana relata atraso na entrega do pedido 8 (previsão vencida em 28/02/2026, rastreio BRJL5544332BR) e solicita verificação.', 'contato': '(67) 99654-7821', 'motivo': 'Previsão de entrega vencida (Pedido 8)'})`

**Assistente** (`gemini-3.5-flash-lite`): Prontinho, Ana! Seu caso foi encaminhado para a nossa equipe com o protocolo EM-20261103-5286. Retornaremos o contato pelo telefone informado em até 24 horas úteis. 

Precisa de mais alguma coisa por enquanto?
