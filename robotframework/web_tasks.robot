*** Settings ***
Documentation     a single test for valid login.
...
...               This test has a workflow that is created using keywords in
...               the imported resource file.
Resource          web_resource.robot

*** Test Cases ***
Valid Login
    Open Browser To Login Page
    Input Credentials
    Submit Credentials
    Welcome Page Should Be Open