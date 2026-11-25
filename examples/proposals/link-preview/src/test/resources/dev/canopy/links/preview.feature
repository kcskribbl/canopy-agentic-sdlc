Feature: Preview a Canopy link without recording a visit

Background:
  * url karate.properties['canopy.baseUrl']
  * configure followRedirects = false

@FR-004 @BR-003 @SEC-003
Scenario: Previewing a saved URL twice does not navigate or count; following it counts once
  * def destination = 'https://reader.invalid/articles/42?q=canopy#part'
  Given path 'api', 'links'
  And request { url: '#(destination)' }
  When method post
  Then status 201
  * def code = response.code
  Given path 'api', 'stats'
  When method get
  * def before = response
  Given path 'api', 'links', code
  When method get
  Then status 200
  And match response == { url: '#(destination)' }
  And match responseHeaders.Location == '#notpresent'
  Given path 'api', 'links', code
  When method get
  Then status 200
  Given path 'api', 'stats'
  When method get
  Then match response == before
  Given path 'r', code
  When method get
  Then status 302
  And match header Location == destination
  Given path 'api', 'stats'
  When method get
  Then match response.totalRedirects == before.totalRedirects + 1

@FR-004 @BR-003
Scenario: Missing preview returns not found without changing totals
  Given path 'api', 'stats'
  When method get
  * def before = response
  Given path 'api', 'links', 'never-issued'
  When method get
  Then status 404
  Given path 'api', 'stats'
  When method get
  Then match response == before
