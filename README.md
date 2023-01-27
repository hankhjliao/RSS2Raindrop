# RSS2Raindrop

## Steps

### The authorization request

```bash
curl "https://api.raindrop.io/v1/oauth/authorize?client_id=<client_id>"
```
Return `<code>`

### Get Token

```bash
curl -X "POST" "https://raindrop.io/oauth/access_token" \
     -H 'Content-Type: application/json' \
     -d $'{
  "grant_type": "authorization_code"
  "code": "<code>",
  "client_id": "<client_id>",
  "client_secret": "<client_secret>",
}'
```
Return `<token>`

### Refresh Token (every 2 weeks)

```bash
curl -X "POST" "https://raindrop.io/oauth/access_token" \
     -H 'Content-Type: application/json' \
     -d $'{
  "grant_type": "refresh_token"
  "refresh_token": "<previous_token>",
  "client_id": "<client_id>",
  "client_secret": "<client_secret>",
}'
```
Return new `<token>`

### [Call raindrop api](https://developer.raindrop.io/v1/authentication/calls)

In header:
```
Authorization: Bearer <token>
```

## Known Issues

## Contributing

Contributions are what make the open source community such an amazing place to be learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See `LICENSE` for more information.

## Contact

Project Link: [https://github.com/hankhjliao/RSS2Raindrop](https://github.com/hankhjliao/RSS2Raindrop)

## Acknowledgements
- [Raindrop API Documents](https://developer.raindrop.io/)
- [README Template](https://github.com/othneildrew/Best-README-Template)

