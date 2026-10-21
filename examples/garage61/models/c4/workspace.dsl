workspace "Гараж 61" "Эталонный проект reqgraph (условный пример)" {

    !identifiers hierarchical

    model {
        client = person "Частный клиент" "Записывается на обслуживание через сайт."
        corp = person "Корпоративный клиент" "Менеджер автопарка, работает по договору."
        admin = person "Администратор" "Управляет расписанием мастеров и записями."

        garage = softwareSystem "Гараж 61: онлайн-запись" "Запись клиентов, напоминания, корпоративные счета." {
            properties {
                "reqgraph.id" "C4-SYS"
            }
            web = container "Веб-приложение" "Сайт для клиентов и кабинет администратора." "Next.js" {
                properties {
                    "reqgraph.id" "C4-CNT-01"
                }
            }
            api = container "API" "Запись, слоты, договоры, счета." "Python, FastAPI" {
                properties {
                    "reqgraph.id" "C4-CNT-02"
                }
            }
            db = container "База данных" "Клиенты, записи, смены, договоры, счета. Размещена в РФ (CON-001)." "PostgreSQL" {
                tags "Database"
                properties {
                    "reqgraph.id" "C4-CNT-03"
                }
            }
            notifier = container "Сервис уведомлений" "Подтверждения и напоминания по SMS." "Python worker" {
                properties {
                    "reqgraph.id" "C4-CNT-04"
                }
            }
        }

        sms = softwareSystem "SMS-шлюз" "Внешний сервис отправки SMS." {
            tags "External"
            properties {
                "reqgraph.id" "C4-EXT-01"
            }
        }

        client -> garage.web "Записывается, отменяет запись" "HTTPS"
        corp -> garage.web "Записывает автомобили, получает счета" "HTTPS"
        admin -> garage.web "Ведёт расписание, отмечает неявки" "HTTPS"
        garage.web -> garage.api "Вызывает" "HTTPS/JSON"
        garage.api -> garage.db "Читает и пишет" "SQL"
        garage.api -> garage.notifier "Ставит задачи на отправку" "очередь в БД"
        garage.notifier -> garage.db "Читает записи для напоминаний" "SQL"
        garage.notifier -> sms "Отправляет SMS" "HTTPS"
        garage.api -> sms "Отправляет SMS-код" "HTTPS"
    }

    views {
        systemContext garage "context" {
            include *
            autolayout lr
        }
        container garage "containers" {
            include *
            autolayout lr
        }
        styles {
            element "Database" {
                shape cylinder
            }
            element "External" {
                background #999999
            }
        }
    }
}
