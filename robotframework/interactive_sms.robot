*** Settings ***
Documentation     Send a request via interactive SMS
...
...               This test has a workflow that is created using keywords in
...               the imported resource file.
Resource          ssh_resource.robot
Suite Setup       Open Connection and Log In
Suite Teardown    Close All Connections

*** Variables ***
${MSISDN}         6590555705
${SHORTCODE}      77755
${MAIN}           mcash
${MAIN_RESP}      Please reply with your option (e.g. 1 or 2)\r\n1. Singtel mRemit
${BALANCE}        balance
${BALANCE_RESP}   balance

*** Test Cases ***
Main Menu
    SMS Simulator Should Contain    ${MAIN}    ${MAIN_RESP}

Balance Check
    SMS Simulator Should Contain    ${BALANCE}    ${BALANCE_RESP}
