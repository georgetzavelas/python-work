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
    TCS Version
    Write   cd TCS
    Read Until    ${PROMPT}

SMS Simulator
    [Arguments]    ${MSISDN}    ${SHORTCODE}    ${menu_keyword}
    Set Client Configuration    prompt=${PROMPT}
    Write         ./scripts/command_line_sms.sh 6060 ${MSISDN} ${SHORTCODE} ${menu_keyword}
    ${output}=    Read Until Prompt
    Log             ${output}
    [Return]      ${output}

SMS Simulator Should Contain
    [Arguments]    ${MSISDN}    ${SHORTCODE}    ${menu_keyword}    ${contains}
    ${output}=    SMS Simulator    ${MSISDN}    ${SHORTCODE}    ${menu_keyword}
    Should Contain    ${output}    ${contains}

TCS Version
    ${version_info}=      TCS CLI       info
    Set Suite Metadata    TCS Version Info    ${version_info}    top=True

TCS CLI
    [Arguments]    ${cli_keywords}
    Write          telnet localhost 6041
    Read Until     TCS>
    Write          ${cli_keywords}
    ${output}=     Read Until       Telepin Software
    Write          quit
    Read Until     Connection to localhost closed by foreign host.
    [Return]       ${output}