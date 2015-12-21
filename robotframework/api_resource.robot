*** Settings ***
Documentation     A resource file with reusable keywords and variables for api interaction
...
Library           RequestsLibrary

*** Variables ***
${URL}            https://10.254.240.161:6060
${SUCCESS}        <Result>0</Result>

*** Keywords ***
TCS XML API Call
    [Arguments]       ${xml}
    Create Session    tcs    ${URL}
    ${headers}=       Create Dictionary  Content-Type=text/xml
    ${resp}=          Post Request    tcs    /telepin    data=${xml}    headers=${headers}
    Should Be Equal As Strings  ${resp.status_code}  200
    Log             ${resp.content}
    Should Contain  ${resp.content}  ${SUCCESS}
    [Return]        ${resp.content}