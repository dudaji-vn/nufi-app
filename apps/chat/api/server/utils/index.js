const handleText = require('./handleText');
const sendEmail = require('./sendEmail');
const queue = require('./queue');
const files = require('./files');
const sessionCookies = require('./sessionCookies');

module.exports = {
  ...handleText,
  sendEmail,
  ...files,
  ...queue,
  ...sessionCookies,
};
