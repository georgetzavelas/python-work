*** Settings ***
Documentation     A resource file with reusable keywords and variables for web interaction
...
...               The system specific keywords created here form our own
...               domain specific language. They utilize keywords provided
...               by the imported Selenium2Library.
Library           Selenium2Library
Library           Dialogs
Suite Teardown    Close Browser

*** Variables ***
${SERVER}         10.254.240.161:8080
${BROWSER}        Chrome
${DELAY}          0
${WEB USER}       admin
${WEB PASSWORD}    tpsingtel1
${LOGIN URL}      http://${SERVER}/mremit-domestic/
${WELCOME URL}    http://${SERVER}/mremit-domestic/MainPortal.html?locale=en
${ERROR URL}      http://${SERVER}/error.html

*** Keywords ***
Open Browser To Login Page
    Open Browser    ${LOGIN URL}    ${BROWSER}
    Set Selenium Speed    ${DELAY}
    Login Page Should Be Open

Login Page Should Be Open
    Title Should Be    Login

Go To Login Page
    Go To    ${LOGIN URL}
    Login Page Should Be Open

Input Credentials
    Input Text    username    ${WEB USER}
    Input Text    password    ${WEB PASSWORD}

Submit Credentials
    Click Element   xpath=//div[@id='isc_7']/table/tbody/tr/td[@class='buttonTitle']

Welcome Page Should Be Open
    Sleep    20s    reason=Waiting for Authentication
    Location Should Be    ${WELCOME URL}
    Title Should Be    Telepin Web
