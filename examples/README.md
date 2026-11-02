# Conversas de exemplo

Conversas longas e completas, capturadas com o agente real e sem edição manual. Cada uma usa uma data simulada coerente com os dados da loja.

| Conversa | Data simulada (`AGENT_NOW`) | O que demonstra |
|---|---|---|
| [Primeira compra](01-primeira-compra.md) | 03/11/2026, 10:00 | Catálogo por faixa de preço, recomendação para iniciante, preço, pagamento combinado, frete, acessórios e dados da loja |
| [Arrependimento e defeito](02-arrependimento-e-defeito.md) | 26/01/2026, 10:30 | Pedido verificado, prazo de arrependimento vencido, troca por defeito dentro do prazo, encaminhamento e garantia |
| [Promoções e catálogo](03-promocoes-e-catalogo.md) | 05/11/2026, 14:00 | Campanha inativa, promoção sem PIX adicional, limite de parcelas, produto sem estoque, descontinuado, em breve, ficha técnica conflitante, categoria vazia e frete para outra cidade |
| [Pedido e reclamação fora do horário](04-pedido-e-reclamacao-fora-do-horario.md) | 01/11/2026, 20:30 (domingo) | Loja fechada, contato errado negado, verificação por e-mail, previsão vencida, reclamação, pedido de terceiro, tentativa de manipulação, fora de escopo e exclusão de dados |

As entradas estão em [`inputs/`](inputs/). Protocolos mudam a cada execução, e as respostas podem variar entre execuções. As conversas 2 e 3 foram recapturadas depois de uma instabilidade do Gemini, em que o modelo de reserva omitiu preços e afirmou um dado sem fonte. Isso também levou a um ajuste no prompt.
