*** Settings ***
Documentation     Send a request the TCS XML API
...

Resource          api_resource.robot

*** Variables ***
${TEST}        <TCSRequest></TCSRequest>
${BALANCE}        <TCSRequest><UserName>6590555705</UserName><TerminalType>STA</TerminalType><Password>11223344b</Password><Function name="BALANCE"></Function></TCSRequest>

*** Test Cases ***
Balance API
    TCS XML API Call    ${BALANCE}
