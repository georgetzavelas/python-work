*** Settings ***
Documentation     Send a request via interactive SMS
...
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
    SMS Simulator Should Contain    ${MSISDN}    ${SHORTCODE}    ${MAIN}    ${MAIN_RESP}

Balance Check
    SMS Simulator Should Contain    ${MSISDN}    ${SHORTCODE}    ${BALANCE}    ${BALANCE_RESP}
