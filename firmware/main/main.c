#include <stdio.h>

#include "audio_stream.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "wifi.h"

static const char *TAG = "main";

void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    ESP_LOGI(TAG, "Initializing Wi-Fi...");
    ESP_ERROR_CHECK(wifi_init_sta());

    ESP_LOGI(TAG, "Starting audio stream task...");
    BaseType_t task_created = xTaskCreate(audio_stream_task, "audio_stream", 4096, NULL, 5, NULL);
    if (task_created != pdPASS) {
        ESP_LOGE(TAG, "Failed to create audio_stream_task");
    }

    // TODO: add additional tasks (control channel, firmware update, etc.).
}

