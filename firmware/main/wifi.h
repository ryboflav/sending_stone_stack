#pragma once

#include "esp_err.h"

/**
 * @brief Initialize Wi-Fi in station mode and connect using sdkconfig credentials.
 */
esp_err_t wifi_init_sta(void);
