*** Settings ***
Documentation     Web related tests
...
Resource          web_resource.robot
Suite Setup       Open Browser and Complete Login

*** Test Cases ***
Open Alarms
    Open Tree Group    Operator Configuration
    Open Tree Item     Alarms
    Sleep    10s    reason=Dramatic Effect
    Close Tab          AlarmsPanel_tab