*** Settings ***
Documentation     A resource file with reusable keywords and variables for ssh interaction
...

Library           SSHLibrary    10 seconds

*** Variables ***
${SERVER}         10.254.240.161
${USERNAME}       telepin
${PASSWORD}       etopup123
${PROMPT}         telepin@dmstt01c:~/TCS$

*** Keywords ***
Open Connection and Log In
    Open Connection    ${SERVER}
    Login   ${USERNAME}    ${PASSWORD}
    Write   cd TCS

SMS Simulator
    [Arguments]        ${menu_keyword}
    Set Client Configuration    prompt=${PROMPT}
    Write         ./scripts/command_line_sms.sh 6060 ${MSISDN} ${SHORTCODE} ${menu_keyword}
    ${output}=    Read Until Prompt
    [Return]      ${output}

SMS Simulator Should Contain
    [Arguments]    ${menu_keyword}    ${contains}
    ${output}=    SMS Simulator    ${menu_keyword}
    Should Contain    ${output}    ${contains}