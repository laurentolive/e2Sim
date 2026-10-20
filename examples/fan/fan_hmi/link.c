/* Fan example - link with the motor board (MIT) */
#include "app.h"
#include "fanProto.h"
#include "halUart.h"
#include "link.h"

static fanProto_parser_t s_parser;
static uint32_t s_lastStatus;
static uint32_t s_lastSend;

void link_Init(void)
{
    halUart_Init(HAL_UART_LINK, 115200);
    fanProto_ParserInit(&s_parser);
    s_lastStatus = app_ms;
    s_lastSend = app_ms;
}

void link_Process(uint32_t now_ms)
{
    uint8_t buf[32];
    size_t n;
    while ((n = halUart_Read(HAL_UART_LINK, buf, sizeof(buf))) != 0u)
    {
        for (size_t i = 0; i < n; i++)
        {
            if (fanProto_Parse(&s_parser, buf[i]) && (s_parser.frame.cmd == FANPROTO_CMD_STATUS) &&
                (s_parser.frame.len == 3u))
            {
                app.rpmMeasured = (uint16_t)(s_parser.frame.payload[0] | (s_parser.frame.payload[1] << 8));
                app.motorFaults = s_parser.frame.payload[2];
                s_lastStatus = now_ms;
            }
        }
    }
    if ((uint32_t)(now_ms - s_lastStatus) > LINK_TIMEOUT_MS)
    {
        app.fault |= APP_FAULT_LINK;
        app.rpmMeasured = 0;
        app.motorFaults = 0;
    }
    else
    {
        app.fault &= ~APP_FAULT_LINK;
    }
    if (app.motorFaults != 0u)
    {
        app.fault |= APP_FAULT_MOTOR;
    }
    else
    {
        app.fault &= ~APP_FAULT_MOTOR;
    }

    if ((uint32_t)(now_ms - s_lastSend) >= LINK_PERIOD_MS)
    {
        s_lastSend = now_ms;
        uint8_t payload[3] = {(uint8_t)app.rpmTarget, (uint8_t)(app.rpmTarget >> 8), (uint8_t)(app.rpmTarget != 0u)};
        uint8_t frame[FANPROTO_MAX_FRAME];
        size_t len = fanProto_Encode(FANPROTO_CMD_SET, payload, sizeof(payload), frame);
        halUart_Write(HAL_UART_LINK, frame, len);
    }
}
