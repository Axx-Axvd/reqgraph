# Официальные XSD BPMN 2.0

Схемы OMG BPMN 2.0 (namespace `http://www.omg.org/spec/BPMN/20100524/MODEL`), без изменений.
По ним `dsl/bpmn_xsd.py` проверяет BPMN, который строит компилятор (проверка SCH-001).

- Авторские права на схемы — Object Management Group (OMG), спецификация BPMN 2.0.
- Источник файлов: jar `org.camunda.bpm.model:camunda-bpmn-model:7.24.0` с Maven Central
  (каталог `org/camunda/bpm/model/bpmn/schema/`, лицензия пакета Apache-2.0). Сайт OMG из облачной
  среды разработки недоступен; Camunda распространяет те же файлы.
- sha256 jar: `49c0d911e5dbe88a7794b1cd2660592d76b7af7622027ee9ad7b97cefcd50674`

| Файл | sha256 |
|---|---|
| BPMN20.xsd | `165ce3c1d9b9bd39ca0e8884cc0fc3ce1940e163d015d9f1c9d910dd3a6a5306` |
| BPMNDI.xsd | `1bfaab6a1e3b4184055100b15d1404e3414601fd47768feb7e932b4cd49fe77f` |
| DC.xsd | `b325cd3c0d03628d5a4e10f78a1e8816b4344a2b35c459b4f5ca1a9c71097590` |
| DI.xsd | `62fa0d89138ac5de62152061be07c899a74e7b983c0486dc6803113e1a5f94a2` |
| Semantic.xsd | `521f69e5a1740a6a9817e213af66546b270e9f00e1a0fb616e7350c8faef83fa` |

Руками не править: при обновлении — заменить файлы целиком и обновить суммы.
