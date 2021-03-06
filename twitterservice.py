import flask
import json
import os
import psycopg2
import psycopg2.extras
import tweepy
import requests
import urllib.parse
from iotmirror_commons.oauth_tokens import AccessTokensDatabase
from iotmirror_commons.oauth_tokens import RequestTokensDatabase
from iotmirror_commons.json_commons import ObjectJSONEncoder
from iotmirror_commons.flask_security import server_secret_key_required
from iotmirror_commons.flask_security import authorizeServerBasicEnvKey


app = flask.Flask(__name__)

app.secret_key = os.environ['APP_SESSION_SECRET_KEY']
consumer_key = os.environ['TWITTER_CONSUMER_KEY']
consumer_secret = os.environ['TWITTER_CONSUMER_KEY_SECRET']
dburl = os.environ['DATABASE_URL']
access_tokens_table = "twitter_access_tokens"
request_tokens_table = "twitter_request_tokens"
atdb = AccessTokensDatabase(dburl,access_tokens_table)
rtdb = RequestTokensDatabase(dburl,request_tokens_table)

#starts signin process for given user
@app.route('/signin/<userID>', methods=['GET'])
def signinUser(userID):
  callback_url = os.environ.get('TWITTER_CALLBACK_URL',None)
  auth = tweepy.OAuthHandler(consumer_key,consumer_secret,callback_url)
  redirect_url = auth.get_authorization_url(True);
  rtdb.insertToken(auth.request_token["oauth_token"],auth.request_token["oauth_token_secret"],userID)
  return flask.redirect(redirect_url)

#exchanges request token for access tokens
@app.route('/signin', methods=['GET'])
def signinComplete():
  oauth_request_token = flask.request.args.get('oauth_token',None)
  oauth_verifier = flask.request.args.get('oauth_verifier',None)
  denied = flask.request.args.get('denied',None)
  if (oauth_request_token is None or oauth_verifier is None) and denied is None:
    return ("<script>close();</script>",400)
  if (denied is not None):
    rtdb.deleteToken(denied)
    return "<script>close();</script>"
  twitter_request_token = rtdb.getToken(oauth_request_token)
  if(twitter_request_token is None):
    return ("<script>close();</script>",404)
  rtdb.deleteToken(oauth_request_token)
  auth = tweepy.OAuthHandler(consumer_key,consumer_secret)
  auth.request_token={"oauth_token":twitter_request_token["request_token"],
                      "oauth_token_secret":twitter_request_token["request_token_secret"]}
  try:
    auth.get_access_token(oauth_verifier)
    atdb.insertUserToken(twitter_request_token["user_id"],auth.access_token,auth.access_token_secret)
  except tweepy.TweepError:
    return ("<script>close();</script>",401)
  except psycopg2.IntegrityError:
    atdb.updateUserToken(twitter_request_token["user_id"],auth.access_token,auth.access_token_secret)
  return "<script>close();</script>"

#deletes request tokens related to the user specified by userID
@app.route('/users/<userID>/request_tokens', methods=['DELETE'])
@server_secret_key_required(authorizeServerBasicEnvKey)
def deleteUserRequestTokens(userID):
  rtdb.deleteUserTokens(userID)
  return ('',204)

#deletes access tokens related to the user specified by userID
@app.route('/users/<userID>/access_tokens', methods=['DELETE'])
@server_secret_key_required(authorizeServerBasicEnvKey)
def deleteUserAccessTokens(userID):
  atdb.deleteUserTokens(userID)
  return ('',204)

#deletes access tokens related to the user specified by userID
@app.route('/signout/<userID>', methods=['DELETE'])
@server_secret_key_required(authorizeServerBasicEnvKey)
def signout(userID):
  return deleteUserAccessTokens(userID)

#returns info about user specified by userID
@app.route('/users/<userID>', methods=['GET'])
@server_secret_key_required(authorizeServerBasicEnvKey)
def userInfo(userID):
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = atdb.getUserToken(userID)
  if(tokens is None):
    return ('',404)
  try:
    auth.set_access_token(tokens["access_token"], tokens["access_token_secret"])
    api = tweepy.API(auth)
    user_data = api.me()
    user = {
             "name" : user_data.name,
             "screen_name" : user_data.screen_name,
             "id" : user_data.id
           }
  except tweepy.TweepError as e:
    return ('',e.response.status_code)
  return json.dumps(user,cls=ObjectJSONEncoder)

#returns tweets form user's (specified by userID) home_timeline
@app.route('/users/<userID>/home_timeline')
@server_secret_key_required(authorizeServerBasicEnvKey)
def tweets(userID):
  max_tweets = 20
  auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
  tokens = atdb.getUserToken(userID)
  if(tokens is None):
    return ('',404)
  auth.set_access_token(tokens["access_token"], tokens["access_token_secret"])
  api = tweepy.API(auth)
  tweets = []
  hashtags = []
  try:
    for status in tweepy.Cursor(api.home_timeline).items(max_tweets):
      tweet = {
                "id" : status.id,
                "text" : status.text,
                "created_at" : status._json['created_at']
              }
      tweet["user"] = {
                        "name" : status.user.name,
                        "screen_name" : status.user.screen_name,
                        "id" : status.user.id
                      }
      tweets.append(tweet)
      hashtags.extend([hashtag['text'] for hashtag in status.entities['hashtags']])
  except tweepy.TweepError as e:
    return ('',e.response.status_code)
  advservice_url = os.environ.get('ADVSERVICE_URL')
  if advservice_url is not None:
    for hashtag in hashtags:
      try:
        requests.put(advservice_url+"/users/"+userID+"/twitter/hashtags/"+hashtag, headers={"Authorization": "Basic "+os.environ.get("SERVERS_SECRET_KEY","")})
      except requests.exceptions.RequestException:
        pass
  return json.dumps(tweets,cls=ObjectJSONEncoder)

if __name__ == '__main__':
  port = int(os.environ.get('PORT',5000))
  app.run(host='0.0.0.0',port=port)

